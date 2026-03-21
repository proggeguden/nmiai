"""Fast parameter sweep: run inference ONCE, then replay post-processing.

Saves per-image raw data (det_scores, cls_probs, dino_probs, mc_predictions),
then sweeps SCORE_CLS_POWER, DINO_WEIGHT, WBF weights etc. in seconds.
"""

import copy
import json
import random
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
COCO_ANN = DATA_DIR / "NM_NGD_coco_dataset" / "annotations.json"
IMAGES_DIR = DATA_DIR / "NM_NGD_coco_dataset" / "images"
SEED = 42
TRAIN_RATIO = 0.9
RAW_CACHE = ROOT / "sweep_cache.json"


def get_val_split():
    with open(COCO_ANN) as f:
        coco_data = json.load(f)
    images = {img["id"]: img for img in coco_data["images"]}
    image_ids = sorted(images.keys())
    random.seed(SEED)
    random.shuffle(image_ids)
    split_idx = int(len(image_ids) * TRAIN_RATIO)
    val_ids = set(image_ids[split_idx:])
    return coco_data, val_ids


def run_inference_with_cache():
    """Run inference once, saving raw per-detection data for replay."""
    # We run the standard pipeline but with a modified run.py that dumps raw data
    # Instead, let's just run validate.py with the current config and cache predictions
    # For the fast sweep, we need the raw det_scores and cls_probs per detection.
    # Simplest approach: run inference once at baseline config, get predictions JSON.
    # Then for score-formula-only changes, recompute scores from raw data.

    # Actually, the cleanest approach: just run validate with each config that changes
    # ONLY the score formula. DET_CONF changes what boxes appear, so that needs re-inference.
    # But SCORE_CLS_POWER, DINO_WEIGHT, WBF weights just rescore existing detections.

    # For now, let's just run the sweep configs that DON'T change detection (no DET_CONF changes)
    # by modifying run.py and running validate. Each run is ~2 min on CPU.
    # We'll batch the fast ones and skip slow re-inference configs.
    pass


def eval_score(coco_data, val_ids, predictions):
    """Compute competition score from predictions."""
    # Detection mAP (category-ignored)
    gt_det = {
        "images": [img for img in coco_data["images"] if img["id"] in val_ids],
        "annotations": [],
        "categories": [{"id": 0, "name": "product"}],
    }
    for ann in coco_data["annotations"]:
        if ann["image_id"] in val_ids:
            gt_det["annotations"].append({**ann, "category_id": 0})

    det_preds = [{"image_id": p["image_id"], "category_id": 0,
                  "bbox": list(p["bbox"]), "score": p["score"]} for p in predictions]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(gt_det, f)
        gt_path = f.name

    try:
        coco_gt = COCO(gt_path)
        coco_dt = coco_gt.loadRes(det_preds) if det_preds else COCO()
        ev = COCOeval(coco_gt, coco_dt, "bbox")
        ev.params.maxDets = [1, 10, 500]
        ev.evaluate()
        ev.accumulate()
        ev.summarize()
        det_map = ev.stats[1]
    finally:
        Path(gt_path).unlink()

    # Classification mAP (per-category)
    gt_cls = {
        "images": [img for img in coco_data["images"] if img["id"] in val_ids],
        "annotations": [a for a in coco_data["annotations"] if a["image_id"] in val_ids],
        "categories": coco_data["categories"],
    }
    cls_preds = [{"image_id": p["image_id"], "category_id": p["category_id"],
                  "bbox": list(p["bbox"]), "score": p["score"]} for p in predictions]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(gt_cls, f)
        gt_path = f.name

    try:
        coco_gt = COCO(gt_path)
        coco_dt = coco_gt.loadRes(cls_preds) if cls_preds else COCO()
        ev = COCOeval(coco_gt, coco_dt, "bbox")
        ev.params.maxDets = [1, 10, 500]
        ev.evaluate()
        ev.accumulate()
        ev.summarize()
        cls_map = ev.stats[1]
    finally:
        Path(gt_path).unlink()

    score = 0.7 * det_map + 0.3 * cls_map
    return det_map, cls_map, score


def run_config(name, config, original_content, coco_data, val_ids):
    """Run a single config: modify run.py, run inference, evaluate."""
    import re

    content = original_content
    for key, value in config.items():
        pattern = rf"^{key}\s*=\s*.*$"
        replacement = f"{key} = {value}"
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

    run_py = ROOT / "run.py"
    run_py.write_text(content)

    # Run inference on val images
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_input = Path(tmpdir) / "images"
        tmp_input.mkdir()
        tmp_output = Path(tmpdir) / "predictions.json"

        id_to_fname = {img["id"]: img["file_name"] for img in coco_data["images"]}
        for img_id in val_ids:
            fname = id_to_fname[img_id]
            src = IMAGES_DIR / fname
            dst = tmp_input / (Path(fname).stem + ".jpg")
            dst.symlink_to(src.resolve())

        result = subprocess.run(
            ["python3", str(ROOT / "run.py"),
             "--input", str(tmp_input),
             "--output", str(tmp_output)],
            capture_output=True, text=True, timeout=1200
        )
        if result.returncode != 0:
            print(f"  FAILED: {result.stderr[-200:]}")
            return name, None, None, None, 0

        with open(tmp_output) as f:
            predictions = json.load(f)

    predictions = [p for p in predictions if p["image_id"] in val_ids]
    det_map, cls_map, score = eval_score(coco_data, val_ids, predictions)
    return name, det_map, cls_map, score, len(predictions)


def main():
    import re

    coco_data, val_ids = get_val_split()
    run_py = ROOT / "run.py"
    original = run_py.read_text()

    # Configs to sweep — FP reduction focus (2026-03-21 evening)
    # Current proven config: KNN=0.1, DINO=0.3, WBF=0.8/0.2, POW=0.7, scored 0.9215 test
    configs = [
        # Baseline (current proven config)
        ("baseline",   {}),
        # MIN_FINAL_SCORE sweep — biggest impact (47% excess FPs)
        ("min_0.05",   {"MIN_FINAL_SCORE": "0.05"}),
        ("min_0.10",   {"MIN_FINAL_SCORE": "0.10"}),
        ("min_0.15",   {"MIN_FINAL_SCORE": "0.15"}),
        ("min_0.20",   {"MIN_FINAL_SCORE": "0.20"}),
        ("min_0.25",   {"MIN_FINAL_SCORE": "0.25"}),
        # Unknown product suppression (cat 355: 67 preds vs 9 GT)
        ("unk_0.1",    {"UNKNOWN_SCORE_BOOST": "0.1"}),
        ("unk_0.2",    {"UNKNOWN_SCORE_BOOST": "0.2"}),
        ("unk_0.3",    {"UNKNOWN_SCORE_BOOST": "0.3"}),
        # WBF skip threshold (raise from 0.01)
        ("wbf_skip_03", {"WBF_SKIP_BOX_THRESH": "0.03"}),
        ("wbf_skip_05", {"WBF_SKIP_BOX_THRESH": "0.05"}),
        ("wbf_skip_10", {"WBF_SKIP_BOX_THRESH": "0.10"}),
        # Best combos (to be refined after individual results)
        ("combo_a",    {"MIN_FINAL_SCORE": "0.10", "UNKNOWN_SCORE_BOOST": "0.2"}),
        ("combo_b",    {"MIN_FINAL_SCORE": "0.15", "UNKNOWN_SCORE_BOOST": "0.2"}),
        ("combo_c",    {"MIN_FINAL_SCORE": "0.10", "WBF_SKIP_BOX_THRESH": "0.05"}),
        ("combo_d",    {"MIN_FINAL_SCORE": "0.15", "WBF_SKIP_BOX_THRESH": "0.05", "UNKNOWN_SCORE_BOOST": "0.2"}),
    ]

    results = []
    for i, (name, config) in enumerate(configs):
        print(f"\n[{i+1}/{len(configs)}] Testing: {name}  {config or '(baseline)'}")
        name, det, cls, score, n_preds = run_config(name, config, original, coco_data, val_ids)
        results.append((name, det, cls, score, n_preds))
        if score:
            print(f"  Det={det:.4f}  Cls={cls:.4f}  Score={score:.4f}  Preds={n_preds}")

    # Restore original
    run_py.write_text(original)

    # Print comparison table
    print(f"\n\n{'='*80}")
    print(f"{'Config':<15} {'Det mAP':<10} {'Cls mAP':<10} {'Score':<10} {'Preds':<8} {'vs current'}")
    print(f"{'-'*80}")
    baseline_score = results[0][3] if results[0][3] else 0
    for name, det, cls, score, preds in sorted(results, key=lambda x: x[3] or 0, reverse=True):
        if score is None:
            continue
        delta = score - baseline_score
        sign = "+" if delta >= 0 else ""
        marker = " ***" if delta > 0.001 else ""
        print(f"{name:<15} {det:<10.4f} {cls:<10.4f} {score:<10.4f} {preds:<8} {sign}{delta:.4f}{marker}")


if __name__ == "__main__":
    main()
