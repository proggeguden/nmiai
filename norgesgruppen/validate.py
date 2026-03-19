"""Evaluate detection mAP@0.5 on validation split using pycocotools."""

import json
from pathlib import Path
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval

DATA_DIR = Path(__file__).parent / "data"
COCO_ANN = DATA_DIR / "NM_NGD_coco_dataset" / "annotations.json"
YOLO_DIR = DATA_DIR / "yolo"


def get_val_image_ids():
    """Get image IDs in the validation split by checking which images are symlinked."""
    val_dir = YOLO_DIR / "images" / "val"
    val_fnames = {p.name for p in val_dir.glob("*.jpg")}

    with open(COCO_ANN) as f:
        coco_data = json.load(f)

    return [img["id"] for img in coco_data["images"] if img["file_name"] in val_fnames]


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", default=None,
                        help="Path to predictions JSON. If not provided, runs inference on val split.")
    args = parser.parse_args()

    val_ids = get_val_image_ids()
    print(f"Validation images: {len(val_ids)}")

    # If no predictions file, run inference
    if args.predictions is None:
        from ultralytics import YOLO
        model_path = Path(__file__).parent / "best.pt"
        if not model_path.exists():
            print(f"Error: {model_path} not found. Train first or provide --predictions.")
            return

        model = YOLO(str(model_path))
        val_dir = YOLO_DIR / "images" / "val"
        image_files = sorted(val_dir.glob("*.jpg"))

        # Build filename -> image_id mapping
        with open(COCO_ANN) as f:
            coco_data = json.load(f)
        fname_to_id = {img["file_name"]: img["id"] for img in coco_data["images"]}

        coco_results = []
        for img_path in image_files:
            results = model.predict(source=str(img_path), imgsz=1280, conf=0.15, max_det=500, verbose=False)
            img_id = fname_to_id[img_path.name]
            for r in results:
                for i in range(len(r.boxes)):
                    x1, y1, x2, y2 = r.boxes.xyxy[i].tolist()
                    conf = r.boxes.conf[i].item()
                    coco_results.append({
                        "image_id": img_id,
                        "category_id": 0,
                        "bbox": [round(x1, 2), round(y1, 2), round(x2 - x1, 2), round(y2 - y1, 2)],
                        "score": round(conf, 4),
                    })
    else:
        # Load predictions from file and convert to COCO eval format
        with open(args.predictions) as f:
            preds = json.load(f)

        with open(COCO_ANN) as f:
            coco_data = json.load(f)
        fname_to_id = {img["file_name"]: img["id"] for img in coco_data["images"]}
        val_fnames = {p.name for p in (YOLO_DIR / "images" / "val").glob("*.jpg")}

        coco_results = []
        for entry in preds:
            if entry["image_id"] not in val_fnames:
                continue
            img_id = fname_to_id[entry["image_id"]]
            for pred in entry["predictions"]:
                coco_results.append({
                    "image_id": img_id,
                    "category_id": 0,
                    "bbox": pred["bbox"],
                    "score": pred["confidence"],
                })

    print(f"Total predictions on val: {len(coco_results)}")

    if not coco_results:
        print("No predictions to evaluate!")
        return

    # Create modified COCO GT with single category for detection-only eval
    gt_data = json.loads(json.dumps(json.load(open(COCO_ANN))))
    gt_data["categories"] = [{"id": 0, "name": "product", "supercategory": "product"}]
    for ann in gt_data["annotations"]:
        ann["category_id"] = 0

    # Filter to val images only
    gt_data["images"] = [img for img in gt_data["images"] if img["id"] in set(val_ids)]
    gt_data["annotations"] = [ann for ann in gt_data["annotations"] if ann["image_id"] in set(val_ids)]

    # Write temp GT file
    tmp_gt = DATA_DIR / "_tmp_val_gt.json"
    with open(tmp_gt, "w") as f:
        json.dump(gt_data, f)

    # Run COCO eval
    coco_gt = COCO(str(tmp_gt))
    coco_dt = coco_gt.loadRes(coco_results)

    coco_eval = COCOeval(coco_gt, coco_dt, "bbox")
    coco_eval.params.iouThrs = [0.5]  # Only mAP@0.5
    coco_eval.evaluate()
    coco_eval.accumulate()
    coco_eval.summarize()

    map50 = coco_eval.stats[0]
    print(f"\nmAP@0.5 (detection only): {map50:.4f}")
    print(f"Estimated competition score (70% weight): {map50 * 0.7:.4f}")

    # Cleanup
    tmp_gt.unlink()


if __name__ == "__main__":
    main()
