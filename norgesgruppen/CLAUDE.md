# NorgesGruppen — Object Detection

## Task
Detect grocery products on store shelves. Scored: 70% detection mAP (IoU>=0.5, category ignored) + 30% classification mAP.

## MVP Strategy
Detection-only: all `category_id=0`. Targets up to 70% of total score.

## Dataset
- `data/NM_NGD_coco_dataset/` — 248 images (2000x1500), 22,731 annotations, 356 categories
- `data/NM_NGD_product_images/` — 345 product folders with 7 angles each
- COCO format: `[x, y, w, h]` absolute pixels, `category_id` 0-355

## Submission
- Entry point: `python run.py --images /data/images/ --output /output/predictions.json`
- Output: `[{"image_id": "img_00042.jpg", "predictions": [{bbox, category_id, confidence}]}]`
- Max 500MB ZIP, 5 submissions/day at app.ainm.no

## Pipeline
1. `convert_coco_to_yolo.py` — COCO → YOLO format, 90/10 split
2. `train.py` — YOLOv8m, imgsz=1280, run on GCP GPU
3. `validate.py` — Local mAP@0.5 eval
4. `run.py` — Inference (submission entry point)
5. `package.py` — Creates submission.zip
