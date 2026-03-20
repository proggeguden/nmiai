# NorgesGruppen — Competition Plan

## Baseline
- YOLOv8m multi-class (356 classes), mAP@0.5 = 0.816
- First submission working (ONNX export, correct format)

## The Key Insight

Single-class detection already hits **0.971 mAP@0.5**. Multi-class YOLO drops to **0.816** because it can't classify 356 products (41 categories have just 1 annotation). **Classification is the bottleneck, not detection.**

Solution: **Two-stage pipeline** — separate detection from classification.

---

## Phase 1: Single-Class YOLOv8l Detector
**Expected gain: +0.03 total score (detection 0.93→0.97)**

- [ ] Add `--single_class` flag to `convert_coco_to_yolo.py`
- [ ] Create `train_detector.py` — YOLOv8l, nc=1, imgsz=1280, batch=4
- [ ] Train on GCP VM (~2-3 hours with early stopping)
- [ ] Export to ONNX (~170MB)

## Phase 2: EfficientNet-B2 Classifier
**Expected gain: +0.06-0.09 total score (classification 0.50→0.75)**

- [ ] Create `extract_crops.py` — crop 22,731 annotations from training images
- [ ] Map reference images (345 folders × 7 angles) to category_ids
- [ ] Create `train_classifier.py` — EfficientNet-B2 (timm), 260×260 input
  - Training data: 22,731 annotation crops + 2,415 reference images
  - Weighted sampling: 1/sqrt(count) per class (fights long-tail)
  - Heavy augmentation: ColorJitter, RandomErasing, RandAugment
  - Oversample reference images 10x for single-annotation classes
  - Label smoothing 0.1
- [ ] Export to ONNX (~35MB)

## Phase 3: Two-Stage Inference Pipeline
**Required to use Phase 1+2**

```
Image → YOLO detect (boxes) → Crop each box → Classify crop → Merge scores → Output
```

- [ ] Rewrite `run.py` for two-stage pipeline
  - YOLO: conf=0.10 (high recall), max_det=500
  - Crop with 5% padding, resize to 260×260
  - Batch classify 64 crops at a time (GPU)
  - Final score = detection_conf × classification_conf
- [ ] Update `package.py` for 3 weight files

**Weight budget**: detector.onnx (170MB) + classifier.onnx (35MB) = **205MB** (< 420MB)
**Time budget**: YOLO ~120s + classify ~25s + overhead ~10s = **~155s** (< 300s)

## Phase 4: Copy-Paste Augmentation
**Expected gain: +0.02-0.04 (boosts rare categories)**

- [ ] Create `copy_paste_augment.py`
  - Paste reference product images onto shelf backgrounds
  - Target: bring every class to ≥50 annotations
  - Generate synthetic COCO annotations
- [ ] Retrain classifier with augmented data

## Phase 5: Ensemble with WBF
**Expected gain: +0.01-0.03 (prediction diversity)**

- [ ] Train multi-class YOLOv8m on augmented data → ONNX (~100MB)
- [ ] Run both pipelines, merge with `ensemble-boxes` WBF
- [ ] Weights: 0.6 two-stage + 0.4 multi-class YOLO

**Weight budget with ensemble**: 170 + 35 + 100 = **305MB** (< 420MB, exactly 3 files)
**Time budget**: ~155s + ~80s + ~2s = **~237s** (< 300s)

## Phase 6: Threshold Tuning
**Expected gain: +0.01-0.02**

- [ ] Sweep conf threshold (0.05-0.30) on validation set
- [ ] Sweep NMS IoU threshold (0.4-0.7)
- [ ] TTA only if time budget allows (not with ensemble)

---

## Score Projection

| Phase | What | Estimated Total Score |
|-------|------|----------------------|
| Baseline | Multi-class YOLOv8m | 0.816 |
| +Phase 1 | YOLOv8l detector | ~0.85 |
| +Phase 2-3 | Two-stage with classifier | ~0.91-0.94 |
| +Phase 4 | Copy-paste augmentation | ~0.93-0.96 |
| +Phase 5 | WBF ensemble | ~0.94-0.97 |
| +Phase 6 | Threshold tuning | ~0.95+ |

## Execution Order
Phases 1 and 2a (crop extraction) run **in parallel** — detector trains on GPU while crops extract on CPU.

## Dataset Stats
- 248 images, 22,731 annotations, 356 categories
- Long-tail: 41 cats with 1 annotation, 158 cats with <20
- Dense: 92 boxes/image average (up to 235)
- Reference images: 345 products × 7 angles = 2,415 (UNUSED — our secret weapon)

## Training Log
| Date | Model | Epochs | Val mAP@0.5 | Notes |
|------|-------|--------|-------------|-------|
| 2026-03-19 | YOLOv8m (nc=1) | 96 (best@46) | 0.971 | Single-class, ultralytics 8.4.24 (incompatible) |
| 2026-03-20 | YOLOv8m (nc=356) | 116 (best@~100) | 0.816 | Multi-class, ultralytics 8.1.0, ONNX export |
