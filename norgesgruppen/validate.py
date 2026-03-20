"""Full competition evaluation: 70% detection mAP@0.5 + 30% classification mAP@0.5.

Usage:
    # Run full two-stage pipeline on val images (needs ONNX models):
    python3 validate.py

    # Evaluate existing predictions JSON (output from run.py):
    python3 validate.py --predictions predictions.json

    # Save per-class results to JSON:
    python3 validate.py --save results.json
"""

import copy
import json
import random
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
COCO_ANN = DATA_DIR / "NM_NGD_coco_dataset" / "annotations.json"
IMAGES_DIR = DATA_DIR / "NM_NGD_coco_dataset" / "images"

SEED = 42
TRAIN_RATIO = 0.9


def get_val_split():
    """Reproduce the exact same val split used by convert_coco_to_yolo.py."""
    with open(COCO_ANN) as f:
        coco_data = json.load(f)

    images = {img["id"]: img for img in coco_data["images"]}
    image_ids = sorted(images.keys())
    random.seed(SEED)
    random.shuffle(image_ids)
    split_idx = int(len(image_ids) * TRAIN_RATIO)
    val_ids = set(image_ids[split_idx:])
    return coco_data, val_ids


def run_inference(coco_data, val_ids):
    """Run the full two-stage pipeline (run.py) on val images."""
    # Create a temp directory with symlinks to val images only
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_input = Path(tmpdir) / "images"
        tmp_input.mkdir()
        tmp_output = Path(tmpdir) / "predictions.json"

        id_to_fname = {img["id"]: img["file_name"] for img in coco_data["images"]}
        for img_id in val_ids:
            fname = id_to_fname[img_id]
            src = IMAGES_DIR / fname
            # Normalize extension to .jpg (run.py only globs *.jpg)
            dst_fname = Path(fname).stem + ".jpg"
            dst = tmp_input / dst_fname
            dst.symlink_to(src.resolve())

        print(f"Running inference on {len(val_ids)} val images...")
        result = subprocess.run(
            ["python3", str(ROOT / "run.py"),
             "--input", str(tmp_input),
             "--output", str(tmp_output)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"Inference failed:\n{result.stderr}")
            return None

        with open(tmp_output) as f:
            predictions = json.load(f)

    print(f"Generated {len(predictions)} predictions")
    return predictions


def load_predictions(pred_path, val_ids):
    """Load predictions JSON and filter to val images only."""
    with open(pred_path) as f:
        predictions = json.load(f)
    predictions = [p for p in predictions if p["image_id"] in val_ids]
    print(f"Loaded {len(predictions)} predictions for {len(val_ids)} val images")
    return predictions


def eval_detection_map(coco_data, val_ids, predictions):
    """Detection mAP@0.5: category-ignored, any correct bbox counts."""
    # GT: collapse all categories to 0
    gt_data = {
        "images": [img for img in coco_data["images"] if img["id"] in val_ids],
        "annotations": [],
        "categories": [{"id": 0, "name": "product", "supercategory": "product"}],
    }
    for ann in coco_data["annotations"]:
        if ann["image_id"] in val_ids:
            gt_data["annotations"].append({
                **ann,
                "category_id": 0,
            })

    # Predictions: collapse all categories to 0 (deep copy to avoid loadRes mutation)
    det_preds = [{"image_id": p["image_id"], "category_id": 0,
                  "bbox": list(p["bbox"]), "score": p["score"]} for p in predictions]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(gt_data, f)
        gt_path = f.name

    try:
        coco_gt = COCO(gt_path)
        coco_dt = coco_gt.loadRes(det_preds) if det_preds else COCO()
        coco_eval = COCOeval(coco_gt, coco_dt, "bbox")
        coco_eval.params.maxDets = [1, 10, 500]
        coco_eval.evaluate()
        coco_eval.accumulate()
        coco_eval.summarize()
        # stats[1] = AP@0.5, stats[0] = AP@0.5:0.95
        return coco_eval.stats[1]
    finally:
        Path(gt_path).unlink()


def eval_classification_map(coco_data, val_ids, predictions):
    """Classification mAP@0.5: per-category AP, then mean across categories with GT."""
    gt_data = {
        "images": [img for img in coco_data["images"] if img["id"] in val_ids],
        "annotations": [ann for ann in coco_data["annotations"] if ann["image_id"] in val_ids],
        "categories": coco_data["categories"],
    }

    # Count GT annotations per category (for reporting)
    gt_counts = defaultdict(int)
    for ann in gt_data["annotations"]:
        gt_counts[ann["category_id"]] += 1

    if not predictions:
        return 0.0, {}

    # Deep copy to avoid loadRes mutation
    cls_preds = [{"image_id": p["image_id"], "category_id": p["category_id"],
                  "bbox": list(p["bbox"]), "score": p["score"]} for p in predictions]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(gt_data, f)
        gt_path = f.name

    try:
        coco_gt = COCO(gt_path)
        coco_dt = coco_gt.loadRes(cls_preds)
        coco_eval = COCOeval(coco_gt, coco_dt, "bbox")
        coco_eval.params.maxDets = [1, 10, 500]
        coco_eval.evaluate()
        coco_eval.accumulate()

        # Extract per-category AP@0.5
        # coco_eval.eval['precision'] shape: (T, R, K, A, M)
        # T=IoU thresholds (10: 0.5:0.05:0.95), R=recall (101), K=categories, A=area (4), M=maxDets (3)
        import numpy as np
        precision = coco_eval.eval["precision"]
        # IoU=0.5 is index 0 in default thresholds, area=all is index 0, maxDets=500 is index 2
        cat_ids = coco_eval.params.catIds
        cat_id_to_name = {cat["id"]: cat["name"] for cat in coco_data["categories"]}

        per_class = {}
        aps = []
        for k_idx, cat_id in enumerate(cat_ids):
            # precision at IoU=0.5, all recall thresholds, this category, all areas, max dets=500
            p = precision[0, :, k_idx, 0, 2]
            if (p == -1).all():
                # No GT for this category in val
                ap = -1.0
            else:
                ap = float(p[p >= 0].mean()) if (p >= 0).any() else 0.0
                aps.append(ap)

            per_class[cat_id] = {
                "name": cat_id_to_name.get(cat_id, f"class_{cat_id}"),
                "ap": ap,
                "gt_count": gt_counts.get(cat_id, 0),
            }

        mean_ap = sum(aps) / len(aps) if aps else 0.0
        return mean_ap, per_class
    finally:
        Path(gt_path).unlink()


def print_results(det_map, cls_map, per_class, coco_data):
    """Print competition score and per-class breakdown."""
    score = 0.7 * det_map + 0.3 * cls_map

    print("\n" + "=" * 70)
    print(f"  Detection mAP@0.5 (category-ignored):  {det_map:.4f}  (× 0.7 = {det_map * 0.7:.4f})")
    print(f"  Classification mAP@0.5 (per-category): {cls_map:.4f}  (× 0.3 = {cls_map * 0.3:.4f})")
    print(f"  COMPETITION SCORE:                      {score:.4f}")
    print("=" * 70)

    # Per-class breakdown sorted by AP (worst first)
    entries = [(cid, info) for cid, info in per_class.items() if info["ap"] >= 0]
    entries.sort(key=lambda x: x[1]["ap"])

    # Count categories with GT in val
    cats_with_gt = [e for e in entries if e[1]["gt_count"] > 0]
    cats_zero_ap = [e for e in cats_with_gt if e[1]["ap"] == 0]

    print(f"\nCategories with GT in val: {len(cats_with_gt)}")
    print(f"Categories with AP = 0:    {len(cats_zero_ap)}")

    # Show worst 30
    print(f"\n{'Rank':<5} {'CatID':<7} {'AP':<8} {'GT':<5} {'Name'}")
    print("-" * 70)
    for rank, (cid, info) in enumerate(entries[:30], 1):
        print(f"{rank:<5} {cid:<7} {info['ap']:<8.4f} {info['gt_count']:<5} {info['name']}")

    # Show best 10
    print(f"\n... Best 10 categories:")
    for cid, info in entries[-10:]:
        print(f"  {cid:<7} {info['ap']:<8.4f} {info['gt_count']:<5} {info['name']}")

    # Category-level stats
    cat_id_to_name = {cat["id"]: cat["name"] for cat in coco_data["categories"]}
    gt_counts_all = defaultdict(int)
    for ann in coco_data["annotations"]:
        gt_counts_all[ann["category_id"]] += 1

    # Categories with NO val data (can't measure)
    cats_no_val = set(gt_counts_all.keys()) - {cid for cid, info in per_class.items() if info["gt_count"] > 0}
    if cats_no_val:
        print(f"\nCategories with NO val annotations ({len(cats_no_val)} total, unmeasurable):")
        for cid in sorted(cats_no_val)[:20]:
            name = cat_id_to_name.get(cid, f"class_{cid}")
            print(f"  {cid:<7} (train: {gt_counts_all[cid]}) {name}")
        if len(cats_no_val) > 20:
            print(f"  ... and {len(cats_no_val) - 20} more")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Full competition evaluation")
    parser.add_argument("--predictions", default=None,
                        help="Path to predictions JSON from run.py. If omitted, runs inference.")
    parser.add_argument("--save", default=None,
                        help="Save detailed results to JSON file")
    args = parser.parse_args()

    coco_data, val_ids = get_val_split()
    print(f"Validation split: {len(val_ids)} images")

    # Get predictions
    if args.predictions:
        predictions = load_predictions(args.predictions, val_ids)
    else:
        predictions = run_inference(coco_data, val_ids)
        if predictions is None:
            return

    # Evaluate detection (category-ignored)
    print("\n--- Detection Evaluation (category-ignored) ---")
    det_map = eval_detection_map(coco_data, val_ids, predictions)

    # Evaluate classification (per-category)
    print("\n--- Classification Evaluation (per-category) ---")
    cls_map, per_class = eval_classification_map(coco_data, val_ids, predictions)

    # Print results
    print_results(det_map, cls_map, per_class, coco_data)

    # Save results
    if args.save:
        results = {
            "detection_map": det_map,
            "classification_map": cls_map,
            "competition_score": 0.7 * det_map + 0.3 * cls_map,
            "per_class": {str(k): v for k, v in per_class.items()},
        }
        with open(args.save, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.save}")

    # Save clean predictions for analyze_results.py
    pred_out = ROOT / "val_predictions.json"
    clean_preds = [{"image_id": p["image_id"], "category_id": p["category_id"],
                    "bbox": list(p["bbox"]), "score": p["score"]} for p in predictions]
    with open(pred_out, "w") as f:
        json.dump(clean_preds, f)
    print(f"Predictions saved to {pred_out}")


if __name__ == "__main__":
    main()
