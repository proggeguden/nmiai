# NorgesGruppen — Object Detection

## Task
Detect grocery products on store shelves. Scored: 70% detection mAP (IoU>=0.5, category ignored) + 30% classification mAP.

## Strategy
Multi-class YOLOv8m with all 357 categories. Targets 100% of total score (70% detection + 30% classification).

## Dataset
- `data/NM_NGD_coco_dataset/` — 248 images (2000x1500), 22,731 annotations, 356 categories
- `data/NM_NGD_product_images/` — 345 product folders with 7 angles each
- COCO format: `[x, y, w, h]` absolute pixels, `category_id` 0-355
- Category 355 = "unknown_product", categories 0-354 are named products
- Train/val split: 223/25 images (90/10, seed=42)

## Submission
- Entry point: `python run.py --input /data/images --output /output/predictions.json`
- Output: `[{"image_id": 42, "category_id": 0, "bbox": [x,y,w,h], "score": 0.923}]`
- Max 420MB uncompressed ZIP, 5 submissions/day at app.ainm.no
- CRITICAL: Pin `ultralytics==8.1.0` (sandbox version)

## Pipeline
1. `convert_coco_to_yolo.py` — COCO → YOLO format, 90/10 split, preserves all 357 categories
2. `train.py` — YOLOv8m, imgsz=1280, 300 epochs, patience=50, heavy augmentation
3. `validate.py` — mAP@0.5 eval with pycocotools (runs inference if no --predictions)
4. `run.py` — Inference entry point (submission), conf=0.15, max_det=500
5. `package.py` — Bundles run.py + best.pt into submission.zip

## GCP Training
```bash
# VM: nmiai-train in europe-west4-a (g2-standard-8, L4 GPU, 100GB disk)
# Project: ai-nm26osl-1788

# SSH into VM
gcloud compute ssh nmiai-train --zone=europe-west4-a --project=ai-nm26osl-1788

# Check training progress
gcloud compute ssh nmiai-train --zone=europe-west4-a --project=ai-nm26osl-1788 \
  --command="tail -20 ~/norgesgruppen/train.log"

# Download best weights after training
gcloud compute scp --zone=europe-west4-a --project=ai-nm26osl-1788 \
  nmiai-train:~/norgesgruppen/runs/detect/runs/detect_mvp/weights/best.pt \
  norgesgruppen/best.pt

# DELETE VM when done (costs money!)
gcloud compute instances delete nmiai-train --zone=europe-west4-a --project=ai-nm26osl-1788
```

## Model Config
| Param | Value | Why |
|-------|-------|-----|
| Model | YOLOv8m | Best accuracy/size tradeoff (~50MB) |
| Resolution | 1280 | Shelf images have many small products |
| Conf threshold | 0.15 | Low threshold maximizes recall for mAP |
| Augmentation | Heavy | Only 248 images — mosaic, mixup, copy_paste, erasing |
| Batch | 4 | Fits L4 24GB VRAM at 1280px with 357 classes |

## Dependencies
```
pip install ultralytics pycocotools
# On headless VM also: sudo apt-get install libgl1-mesa-glx libglib2.0-0
```
