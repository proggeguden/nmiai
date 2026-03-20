# NorgesGruppen — Object Detection

## Task
Detect grocery products on store shelves. Scored: 70% detection mAP (IoU>=0.5, category ignored) + 30% classification mAP.

## Strategy
Two-stage pipeline: single-class YOLOv8l detector + EfficientNet-B2 classifier with kNN embedding ensemble.

## Dataset
- `data/NM_NGD_coco_dataset/` — 248 images (variable resolution), 22,731 annotations, 356 categories
- `data/NM_NGD_product_images/` — 345 product folders (barcode-named), 5-7 angles each, mapped via `metadata.json`
- COCO format: `[x, y, w, h]` absolute pixels, `category_id` 0-355
- Category 355 = "unknown_product", categories 0-354 are named products
- Train/val split: 223/25 images (90/10, seed=42)
- Long-tail: 41 categories have 1 annotation, 158 have <20

## Submission
- Entry point: `python run.py --input /data/images --output /output/predictions.json`
- Output: `[{"image_id": 42, "category_id": 0, "bbox": [x,y,w,h], "score": 0.923}]`
- Max 420MB uncompressed ZIP, 3 weight files max, 5 submissions/day at app.ainm.no
- CRITICAL: Pin `ultralytics==8.1.0`, `torch==2.6.0`, `timm==0.9.12` (sandbox versions)
- Security: no os, sys, subprocess, pickle, yaml. Use pathlib + json.

## Pipeline
### Training
1. `convert_coco_to_yolo.py` — COCO → YOLO format, supports `--single_class` flag
2. `train_detector.py` — YOLOv8l single-class, imgsz=1280, batch=2
3. `extract_crops.py` — crop annotations + map reference images via metadata.json barcode→category
4. `train_classifier.py` — EfficientNet-B2 (timm), 260×260, batch=192, AMP, weighted sampling
5. `precompute_embeddings.py` — extract classifier features for kNN, export dual-output ONNX

### Inference (run.py)
1. YOLO detect (conf=0.10, max_det=500) → bounding boxes
2. Crop each detection (5% padding) → resize 260×260
3. Classify: EfficientNet-B2 → logits + features (one forward pass)
4. kNN: cosine similarity to precomputed embeddings → vote distribution
5. Ensemble: 0.6 × classifier_softmax + 0.4 × knn_vote
6. Final score = detection_conf × classification_conf

### Packaging
6. `package.py` — bundles run.py + detector.onnx + classifier.onnx + embeddings.npy

## GCP Training
```bash
# VM: nmiai-train in europe-west4-a (g2-standard-16, L4 GPU, 100GB disk)
# Project: ai-nm26osl-1788

gcloud compute ssh nmiai-train --zone=europe-west4-a --project=ai-nm26osl-1788

# Check training
tail -10 ~/norgesgruppen/train_classifier.log
tail -10 ~/norgesgruppen/train_detector.log

# After classifier finishes:
python3 precompute_embeddings.py

# Download results
gcloud compute scp --zone=europe-west4-a --project=ai-nm26osl-1788 \
  nmiai-train:~/norgesgruppen/classifier.onnx norgesgruppen/classifier.onnx
gcloud compute scp --zone=europe-west4-a --project=ai-nm26osl-1788 \
  nmiai-train:~/norgesgruppen/embeddings.npy norgesgruppen/embeddings.npy

# DELETE VM when done (costs money!)
gcloud compute instances delete nmiai-train --zone=europe-west4-a --project=ai-nm26osl-1788
```

## Weight Budget
| File | Size | Purpose |
|------|------|---------|
| detector.onnx | 167MB | YOLOv8l single-class detection |
| classifier.onnx | ~35MB | EfficientNet-B2 dual-output (logits + features) |
| embeddings.npy | ~50MB | Precomputed kNN embeddings |
| **Total** | **~252MB** | < 420MB limit ✓ |

## Dependencies
```
pip install ultralytics==8.1.0 timm==0.9.12
pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
```
