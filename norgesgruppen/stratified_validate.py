"""Stratified validation: ensure every category with annotations appears in val.

The original 90/10 image-level split leaves 229/356 categories with ZERO val data.
This script uses a stratified approach: for each category, hold out ~10% of its
annotations by selecting images that maximize category coverage in val.

Usage:
    python3 stratified_validate.py
    python3 stratified_validate.py --predictions predictions.json
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


def build_stratified_split(coco_data, val_ratio=0.15):
    """Select val images to maximize category coverage.

    Strategy: greedily pick images that cover the most uncovered categories,
    until we have ~val_ratio of images.
    """
    random.seed(SEED)

    # Map image_id → set of category_ids in that image
    img_cats = defaultdict(set)
    # Map category_id → set of image_ids containing it
    cat_imgs = defaultdict(set)

    for ann in coco_data["annotations"]:
        img_cats[ann["image_id"]].add(ann["category_id"])
        cat_imgs[ann["category_id"]].add(ann["image_id"])

    all_img_ids = sorted(img_cats.keys())
    all_cat_ids = set(cat_imgs.keys())
    target_val_count = max(1, int(len(all_img_ids) * val_ratio))

    val_ids = set()
    covered_cats = set()

    # Phase 1: Greedy — pick images that cover the most new categories
    remaining = set(all_img_ids)
    while len(val_ids) < target_val_count and remaining:
        best_img = None
        best_new = -1

        for img_id in remaining:
            new_cats = len(img_cats[img_id] - covered_cats)
            if new_cats > best_new:
                best_new = new_cats
                best_img = img_id

        if best_img is None or best_new == 0:
            break

        val_ids.add(best_img)
        covered_cats |= img_cats[best_img]
        remaining.discard(best_img)

    # Phase 2: Fill remaining val slots randomly
    remaining_list = sorted(remaining)
    random.shuffle(remaining_list)
    while len(val_ids) < target_val_count and remaining_list:
        val_ids.add(remaining_list.pop())

    # Stats
    val_ann_count = sum(1 for ann in coco_data["annotations"] if ann["image_id"] in val_ids)
    val_cats = set()
    for ann in coco_data["annotations"]:
        if ann["image_id"] in val_ids:
            val_cats.add(ann["category_id"])

    uncovered = all_cat_ids - val_cats
    print(f"Stratified split: {len(val_ids)} val images, {len(all_img_ids) - len(val_ids)} train images")
    print(f"Val annotations: {val_ann_count}")
    print(f"Categories covered in val: {len(val_cats)}/{len(all_cat_ids)}")
    if uncovered:
        print(f"Uncovered categories: {len(uncovered)} (only appear in train)")

    return val_ids


def run_inference(coco_data, val_ids):
    """Run run.py on val images."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_input = Path(tmpdir) / "images"
        tmp_input.mkdir()
        tmp_output = Path(tmpdir) / "predictions.json"

        id_to_fname = {img["id"]: img["file_name"] for img in coco_data["images"]}
        for img_id in val_ids:
            fname = id_to_fname[img_id]
            src = IMAGES_DIR / fname
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
            print(f"Inference failed:\n{result.stderr[-500:]}")
            return None

        with open(tmp_output) as f:
            predictions = json.load(f)

    print(f"Generated {len(predictions)} predictions")
    return predictions


def eval_map(coco_data, val_ids, predictions, category_aware=True):
    """Run COCO eval. If category_aware=False, collapse all to single class."""
    gt_data = {
        "images": [img for img in coco_data["images"] if img["id"] in val_ids],
        "annotations": [ann for ann in coco_data["annotations"] if ann["image_id"] in val_ids],
        "categories": coco_data["categories"],
    }

    preds = [{"image_id": p["image_id"], "category_id": p["category_id"],
              "bbox": list(p["bbox"]), "score": p["score"]} for p in predictions]

    if not category_aware:
        gt_data = copy.deepcopy(gt_data)
        gt_data["categories"] = [{"id": 0, "name": "product", "supercategory": "product"}]
        for ann in gt_data["annotations"]:
            ann["category_id"] = 0
        preds = [{"image_id": p["image_id"], "category_id": 0,
                  "bbox": list(p["bbox"]), "score": p["score"]} for p in predictions]

    if not preds:
        return 0.0, {}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(gt_data, f)
        gt_path = f.name

    try:
        coco_gt = COCO(gt_path)
        coco_dt = coco_gt.loadRes(preds)
        coco_eval = COCOeval(coco_gt, coco_dt, "bbox")
        coco_eval.params.maxDets = [1, 10, 500]
        coco_eval.evaluate()
        coco_eval.accumulate()
        coco_eval.summarize()

        import numpy as np
        map50 = coco_eval.stats[1]  # AP@0.5

        # Per-class AP if category-aware
        per_class = {}
        if category_aware:
            precision = coco_eval.eval["precision"]
            cat_ids = coco_eval.params.catIds
            cat_names = {cat["id"]: cat["name"] for cat in coco_data["categories"]}
            gt_counts = defaultdict(int)
            for ann in gt_data["annotations"]:
                gt_counts[ann["category_id"]] += 1

            aps = []
            for k_idx, cat_id in enumerate(cat_ids):
                p = precision[0, :, k_idx, 0, 2]
                if (p == -1).all():
                    ap = -1.0
                else:
                    ap = float(p[p >= 0].mean()) if (p >= 0).any() else 0.0
                    aps.append(ap)
                per_class[cat_id] = {
                    "name": cat_names.get(cat_id, f"class_{cat_id}"),
                    "ap": ap,
                    "gt_count": gt_counts.get(cat_id, 0),
                }
            map50 = sum(aps) / len(aps) if aps else 0.0

        return map50, per_class
    finally:
        Path(gt_path).unlink()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", default=None)
    parser.add_argument("--save", default=None)
    args = parser.parse_args()

    with open(COCO_ANN) as f:
        coco_data = json.load(f)

    val_ids = build_stratified_split(coco_data, val_ratio=0.15)

    if args.predictions:
        with open(args.predictions) as f:
            predictions = json.load(f)
        predictions = [p for p in predictions if p["image_id"] in val_ids]
    else:
        predictions = run_inference(coco_data, val_ids)
        if predictions is None:
            return

    print("\n--- Detection mAP (category-ignored) ---")
    det_map, _ = eval_map(coco_data, val_ids, predictions, category_aware=False)

    print("\n--- Classification mAP (per-category) ---")
    cls_map, per_class = eval_map(coco_data, val_ids, predictions, category_aware=True)

    score = 0.7 * det_map + 0.3 * cls_map
    print(f"\n{'='*70}")
    print(f"  Detection mAP@0.5:       {det_map:.4f}  (× 0.7 = {det_map * 0.7:.4f})")
    print(f"  Classification mAP@0.5:  {cls_map:.4f}  (× 0.3 = {cls_map * 0.3:.4f})")
    print(f"  COMPETITION SCORE:       {score:.4f}")
    print(f"{'='*70}")

    # Show worst categories
    entries = [(cid, info) for cid, info in per_class.items() if info["gt_count"] > 0]
    entries.sort(key=lambda x: x[1]["ap"])
    cats_zero = [e for e in entries if e[1]["ap"] == 0]
    print(f"\nCategories with GT in val: {len(entries)}")
    print(f"Categories with AP = 0:    {len(cats_zero)}")

    print(f"\nWorst 20:")
    for rank, (cid, info) in enumerate(entries[:20], 1):
        print(f"  {rank:<3} cat {cid:<5} AP={info['ap']:.4f}  GT={info['gt_count']:<4} {info['name']}")

    if args.save:
        results = {
            "detection_map": det_map,
            "classification_map": cls_map,
            "competition_score": score,
            "per_class": {str(k): v for k, v in per_class.items()},
            "val_image_count": len(val_ids),
            "val_category_count": len(entries),
        }
        with open(args.save, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.save}")


if __name__ == "__main__":
    main()
