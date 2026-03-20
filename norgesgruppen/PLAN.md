# NorgesGruppen — Competition Plan

## Baseline
- Multi-class YOLOv8m: mAP@0.5 = 0.816 (first submission, working)

## Current: Two-Stage Pipeline + kNN Ensemble

### Phase 1: Single-Class YOLOv8l Detector ✅
- [x] Add `--single_class` flag to convert_coco_to_yolo.py
- [x] Train YOLOv8l (nc=1) — mAP@0.5 = **0.967** at epoch 40
- [x] Export to ONNX (167MB)
- [x] Downloaded locally

### Phase 2: EfficientNet-B2 Classifier (in progress)
- [x] Extract 22,731 annotation crops from training images
- [x] Map 1,577 reference images via metadata.json (326 folders matched)
- [x] Train EfficientNet-B2: batch=192, AMP, weighted sampling
- [ ] **TRAINING**: Epoch 28/80, val_acc = **89.8%** (~45 min left)
- [ ] Run precompute_embeddings.py (extract features + export dual-output ONNX)
- [ ] Download classifier.onnx + embeddings.npy

### Phase 3: Two-Stage Inference Pipeline ✅
- [x] run.py: YOLO detect → crop → classify → kNN ensemble → merge scores
- [x] Graceful fallback (works without embeddings.npy)
- [x] package.py: 3 weight files (detector + classifier + embeddings)
- [ ] Test locally
- [ ] Submit at app.ainm.no

### Phase 4: Optimization (next)
- [ ] Classification TTA (flip + rotate crops, average predictions)
- [ ] Soft-NMS instead of hard NMS
- [ ] Confidence threshold tuning on validation set
- [ ] Per-class threshold optimization
- [ ] Knowledge distillation from multi-class YOLO (soft labels)

### Phase 5: Advanced (if time permits)
- [ ] DINOv2 embeddings as alternative/additional kNN backbone
- [ ] Copy-paste augmentation for rare classes
- [ ] Multi-class YOLO ensemble via WBF
- [ ] Tile-based inference for dense regions
- [ ] Temperature scaling for confidence calibration

## Score Projection

| Stage | What | Estimated Score |
|-------|------|----------------|
| Baseline | Multi-class YOLOv8m | 0.816 |
| +Phase 1 | YOLOv8l detector (0.967 det) | ~0.85 |
| +Phase 2 | EfficientNet-B2 classifier (~90%) | ~0.91-0.94 |
| +Phase 3 | kNN ensemble (+2-3% cls) | ~0.93-0.96 |
| +Phase 4 | TTA + Soft-NMS + tuning | ~0.95+ |

## Dataset Insights
- 248 images, 22,731 annotations, 356 categories
- Long-tail: 41 cats with 1 annotation, 158 cats with <20
- Dense: 92 boxes/image avg (up to 235), 97% images have overlapping boxes
- 42% of boxes on image edges (truncation risk)
- Reference images: 345 products × 5-7 angles = 1,577 images (mapped via barcode)
- Confusable products: 11 WASA variants, 8 granola variants, 5 Nescafé variants
- 35 categories have NO reference images

## Training Log
| Date | Model | Epochs | Metric | Notes |
|------|-------|--------|--------|-------|
| 03-19 | YOLOv8m (nc=1) | 96 (best@46) | mAP=0.971 | ultralytics 8.4.24 (incompatible) |
| 03-20 | YOLOv8m (nc=356) | 116 (best@~100) | mAP=0.816 | First submission, ONNX |
| 03-20 | YOLOv8l (nc=1) | 54 (best@~40) | mAP=0.967 | OOM at batch=4, used batch=2 |
| 03-20 | EfficientNet-B2 | 28/80 | acc=89.8% | batch=192, AMP, 356 classes |
