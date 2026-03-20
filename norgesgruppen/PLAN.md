# NorgesGruppen — Competition Plan

## Completed

### Phase 1: Detection MVP ✅
- Multi-class YOLOv8m → mAP@0.5 = 0.816
- First working submission (ONNX, correct format)

### Phase 2: Two-Stage Pipeline ✅
- YOLOv8l single-class detector → mAP@0.5 = 0.967
- EfficientNet-B2 classifier → 90.8% val accuracy (356 classes)
- kNN embedding ensemble (24,308 embeddings, cosine similarity)
- Dual-output ONNX (logits + features in one forward pass)
- Two-stage run.py: detect → crop → classify → kNN → ensemble
- Submission: 329MB total (detector 167MB + classifier 31MB + embeddings 131MB)

## In Progress

### VM2: Multi-class YOLO for WBF Ensemble
- Training on `nmiai-train-multiclass` (europe-west1-c)
- YOLOv8m, nc=356, batch=4, imgsz=1280
- Will be used as ensemble member with WBF (ensemble-boxes)

## Next Improvements (Priority Order)

### 1. WBF Ensemble (expected +1-3%)
- Combine two-stage pipeline + multi-class YOLO predictions
- Use `ensemble-boxes` library (pre-installed in sandbox)
- Weights: 0.6 two-stage + 0.4 multi-class YOLO
- **Requires**: multi-class YOLO ONNX from VM2

### 2. Classification TTA (expected +2-3%)
- For each crop: classify original + horizontal flip + 2 rotations
- Average softmax probabilities before argmax
- Costs ~4x classifier time (~80s extra), fits within 300s budget

### 3. Soft-NMS (expected +1-2%)
- Replace hard NMS with soft-NMS in run.py
- Decay overlapping box scores instead of removing
- Critical for dense shelves (97% images have overlapping boxes)

### 4. Confidence Threshold Tuning (expected +1%)
- Sweep detection conf (0.05-0.30) on validation set
- Sweep NMS IoU threshold (0.4-0.7)
- Per-class threshold optimization

### 5. Knowledge Distillation (expected +2-4%)
- Use multi-class YOLO's softmax outputs as soft labels
- Retrain classifier with KL-divergence loss
- Transfers "dark knowledge" about product similarity

### 6. DINOv2 Embeddings (expected +2-3%)
- `vit_small_patch14_dinov2.lvd142m` from timm 0.9.12
- Alternative/additional kNN backbone alongside classifier features
- Would replace embeddings.npy (need to fit in 3 weight file limit)

### 7. Copy-Paste Augmentation (expected +1-2%)
- Paste reference product images onto shelf backgrounds
- Bring every class to ≥50 training samples
- Retrain both classifier and multi-class YOLO

## Training Log
| Date | Model | Epochs | Metric | Notes |
|------|-------|--------|--------|-------|
| 03-19 | YOLOv8m (nc=1) | 96 | mAP=0.971 | ultralytics 8.4.24 (incompatible) |
| 03-20 | YOLOv8m (nc=356) | 116 | mAP=0.816 | First submission, ONNX |
| 03-20 | YOLOv8l (nc=1) | 54 | mAP=0.967 | batch=2, exported to ONNX |
| 03-20 | EfficientNet-B2 | 80 | acc=90.8% | batch=192, AMP, 356 classes |
| 03-20 | YOLOv8m (nc=356) | training... | TBD | VM2, for WBF ensemble |

## Key Dataset Insights
- 328/356 categories have reference images (92% coverage)
- 35 categories have NO reference images
- 141 categories have ≤20 annotation crops (high-risk)
- 11 WASA knekkebrød variants differ only by weight text
- Average 92 boxes/image, up to 235
- 42% of boxes on image edges (truncation)
