# NorgesGruppen — Object Detection

## Local Files
Weight files (`.onnx`, `.npy`, `.pt`) are gitignored. They live in `norgesgruppen/` on main:
- `detector.onnx` (167MB), `classifier.onnx` (31MB), `embeddings.npy` (131MB), `submission.zip`
- When using a worktree, symlink them: `ln -s ~/Desktop/nmiai/code/nmiai/norgesgruppen/*.onnx .`
- Training data lives in `norgesgruppen/data/` (also gitignored) — must exist locally and on GCP VMs

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
- Confusable: 11 WASA knekkebrød variants, 8 granola, 5 Nescafé
- 97% of images have overlapping boxes, 42% of boxes on image edges

## Submission
- Entry point: `python run.py --input /data/images --output /output/predictions.json`
- Output: `[{"image_id": 42, "category_id": 0, "bbox": [x,y,w,h], "score": 0.923}]`
- Max 420MB uncompressed ZIP, 3 weight files max, 5 submissions/day at app.ainm.no
- CRITICAL: Pin `ultralytics==8.1.0`, `torch==2.6.0`, `timm==0.9.12` (sandbox versions)
- Security: no os, sys, subprocess, pickle, yaml. Use pathlib + json.
- Sandbox: L4 GPU, 300s timeout, 8GB RAM, no network

## Pipeline
### Training Scripts
1. `convert_coco_to_yolo.py` — COCO → YOLO format, supports `--single_class` flag
2. `train_detector.py` — YOLOv8l single-class, imgsz=1280, batch=2. Flags: `--augmented`, `--aggressive-aug`
3. `extract_crops.py` — crop annotations + map reference images via metadata.json barcode→category
4. `train_classifier.py` — EfficientNet-B2 (timm), 260×260, batch=192, AMP, weighted sampling. Flags: `--letterbox`, `--arcface`, `--aggressive-aug`
5. `precompute_embeddings.py` — extract classifier features for kNN, export dual-output ONNX. Flags: `--letterbox`, `--arcface`
6. `train.py` — Multi-class YOLOv8m (for WBF ensemble, future use)
7. `copy_paste_augment.py` — Generate synthetic training images via copy-paste augmentation (rare class focus)
8. `train_dino_classifier.py` — DINOv2-ViT-S classifier (robust features). Flags: `--letterbox`, `--aggressive-aug`
9. `build_dual_classifier.py` — Merge EfficientNet-B2 + DINOv2 into single ONNX (4 outputs)
10. `train_rtdetr.py` — RT-DETR-L transformer detector (ensemble diversity). Flag: `--augmented`

### Inference (run.py)
1. YOLO detect (conf=0.10, max_det=500) → bounding boxes (hard NMS, IoU=0.5)
2. Crop each detection (5% padding) → resize 260×260
3. TTA: 4 augmented variants per crop (original, flip, ±5° rotation)
4. Classify: EfficientNet-B2 → logits + features (one forward pass, dual-output ONNX)
   - If dual-backbone ONNX (4 outputs): also runs DINOv2, ensembles 0.5×EfficientNet + 0.5×DINOv2
5. Average TTA softmax probabilities + feature vectors
6. kNN: cosine similarity to precomputed embeddings → vote distribution
7. Ensemble: 0.6 × classifier_softmax + 0.4 × knn_vote
8. WBF fusion with multi-class YOLO (uses `ensemble_boxes` library if available, else custom NMS)
9. Final score = detection_conf × classification_conf^0.7
10. Graceful fallback: works without embeddings.npy (classifier-only mode)

### Diagnostics & Tools
- `validate.py` — full 70/30 competition scoring with per-class AP breakdown
- `analyze_results.py` — annotated val images, confusion report, crop galleries
- `shopping_list.py` — prioritized products to photograph at the store
- `add_photos.py` — integrate user photos into training pipeline (`data/user_photos/{cat_id}/`)
- `sweep.py` — automated A/B testing of run.py hyperparameters

### Packaging
- `package.py` — bundles run.py + detector.onnx + classifier.onnx + embeddings.npy

## GCP Training
```bash
# VM1: nmiai-train in europe-west4-a (g2-standard-16, L4 GPU)
# VM2: nmiai-train-multiclass in europe-west1-c (g2-standard-8, L4 GPU)
# Project: ai-nm26osl-1788

# SSH
gcloud compute ssh nmiai-train --zone=europe-west4-a --project=ai-nm26osl-1788
gcloud compute ssh nmiai-train-multiclass --zone=europe-west1-c --project=ai-nm26osl-1788

# IMPORTANT: Use separate VMs for each training job, never queue sequentially

# After training, export + download:
# On VM: python3 precompute_embeddings.py
# Local: gcloud compute scp ... nmiai-train:~/norgesgruppen/classifier.onnx norgesgruppen/
# Local: gcloud compute scp ... nmiai-train:~/norgesgruppen/embeddings.npy norgesgruppen/

# DELETE VMs when done (costs money!)
gcloud compute instances delete nmiai-train --zone=europe-west4-a --project=ai-nm26osl-1788
gcloud compute instances delete nmiai-train-multiclass --zone=europe-west1-c --project=ai-nm26osl-1788
```

## Current Results
| Metric | Value |
|--------|-------|
| **Competition score (local val)** | **0.9392** |
| Detection mAP@0.5 (category-ignored) | 0.959 |
| Classification mAP@0.5 (per-category) | 0.893 |
| Detection recall | 97.4% |
| Classification accuracy (matched det) | 96.6% |
| Categories with AP=0 in val | 10 |
| Categories with NO val data | 134 |

### Known Weaknesses
- **Egg products**: 40/71 misclassifications (56%). 6-pack vs 12-pack Prior eggs = 16 confusions alone.
- **10 categories with AP=0**: Jacobs Gårdsegg, Grissini, Lady Grey, Müsli Frukt, etc.
- **134 categories unmeasurable**: no val annotations (10% image-level split too coarse for 356 classes)
- **Soft-NMS hurts**: generates excess FPs on dense shelves, −0.003 score

## Weight Budget
| File | Size | Purpose |
|------|------|---------|
| detector.onnx | 167MB | YOLOv8l single-class detection |
| classifier.onnx | 31MB | EfficientNet-B2 dual-output (logits + features) |
| embeddings.npy | 131MB | 24,308 precomputed kNN embeddings |
| **Total** | **329MB** | < 420MB limit ✓ |

## Dependencies
```
pip install ultralytics==8.1.0 timm==0.9.12 onnxruntime-gpu
pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
# On headless VM: sudo apt-get install libgl1-mesa-glx libglib2.0-0
```
