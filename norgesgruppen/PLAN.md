# NorgesGruppen — Competition Plan

## Current Score: 0.9392 (local val)
- Detection mAP@0.5: 0.959 (× 0.7 = 0.671)
- Classification mAP@0.5: 0.893 (× 0.3 = 0.268)

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

### Phase 3: Diagnostics & Inference Tuning ✅
- Full competition validation: 70/30 scoring with per-class AP breakdown
- Visual diagnostics: annotated val images, confusion report, crop galleries
- Hyperparameter sweep: tested TTA, Soft-NMS, score formula variants
- Best config: TTA (4 augments) + score=det×cls^0.7 → 0.9392 (+0.0009)
- Soft-NMS tested and rejected (hurts: −0.003 due to excess FPs)
- Shopping list + photo integration pipeline ready

### Sweep Results (2025-03-20)
| Config | Det mAP | Cls mAP | Score | vs baseline |
|--------|---------|---------|-------|-------------|
| baseline | 0.959 | 0.890 | 0.9383 | — |
| tta_only | 0.959 | 0.891 | 0.9387 | +0.0004 |
| tta+sqrt | 0.959 | 0.892 | 0.9388 | +0.0005 |
| **tta+pow07** | **0.959** | **0.893** | **0.9392** | **+0.0009** |
| softnms_only | 0.955 | 0.889 | 0.9354 | −0.0029 |
| softnms+tta | 0.956 | 0.891 | 0.9361 | −0.0022 |

## In Progress

### VM2: Multi-class YOLO for WBF Ensemble
- Training on `nmiai-train-multiclass` (europe-west1-c)
- YOLOv8m, nc=356, batch=4, imgsz=1280
- Epoch 117/300, val mAP@0.5 = 0.813 (as of 2025-03-20 16:00)

### User Photography Campaign
- Shopping list generated (`shopping_list.txt`)
- Priority: egg products (40/71 confusions), categories with AP=0, categories with no ref images
- Photo pipeline ready: `add_photos.py` → augment → retrain

## Next Improvements (Priority Order)

### 1. User Photos for Weak Categories (expected +2-5%)
- Photograph egg variants, AP=0 categories, confusable products
- Integrate via add_photos.py → retrain classifier + re-embed
- **Biggest expected gain**: egg products alone are 56% of all errors

### 2. WBF Ensemble (expected +1-3%)
- Combine two-stage pipeline + multi-class YOLO predictions
- Use `ensemble-boxes` library (pre-installed in sandbox)
- Weights: 0.6 two-stage + 0.4 multi-class YOLO
- **Requires**: multi-class YOLO ONNX from VM2

### 3. Confidence Threshold Tuning (expected +0.5-1%)
- Sweep detection conf (0.05-0.30) on validation set
- Sweep NMS IoU threshold (0.4-0.7)
- Use sweep.py framework

### 4. Knowledge Distillation (expected +2-4%)
- Use multi-class YOLO's softmax outputs as soft labels
- Retrain classifier with KL-divergence loss
- **Requires**: multi-class YOLO ONNX from VM2

### 5. DINOv2 Embeddings (expected +2-3%)
- `vit_small_patch14_dinov2.lvd142m` from timm 0.9.12
- Alternative/additional kNN backbone alongside classifier features
- Would replace embeddings.npy (need to fit in 3 weight file limit)

### 6. Copy-Paste Augmentation (expected +1-2%)
- Paste reference product images onto shelf backgrounds
- Bring every class to ≥50 training samples
- Retrain both classifier and multi-class YOLO

## Key Classification Failures (from analyze_results.py)

### Egg Products (40 confusions = 56% of all errors)
- 16× EGG FRITTGÅENDE M/L 6PK ← EGG FRITTGÅENDE 12STK (Prior)
- 7× SOLEGG 6STK ← SOLEGG 12STK
- 3× EGG ØKOLOGISK ← FROKOSTEGG
- Various farm eggs confused (Galåvolden, Tørresvik, Leka)

### Other Confusions
- Lady Grey TEA 25pos vs 200g (3×)
- Evergood kokmalt vs filtermalt (2×)
- Ali filtermalt vs kokmalt (2×)
- Nescafe Gold variants (5 total)
- Granola/Müsli variants (5 total)

## Training Log
| Date | Model | Epochs | Metric | Notes |
|------|-------|--------|--------|-------|
| 03-19 | YOLOv8m (nc=1) | 96 | mAP=0.971 | ultralytics 8.4.24 (incompatible) |
| 03-20 | YOLOv8m (nc=356) | 116 | mAP=0.816 | First submission, ONNX |
| 03-20 | YOLOv8l (nc=1) | 54 | mAP=0.967 | batch=2, exported to ONNX |
| 03-20 | EfficientNet-B2 | 80 | acc=90.8% | batch=192, AMP, 356 classes |
| 03-20 | YOLOv8m (nc=356) | 117/300 | mAP=0.813 | VM2, still training |
| 03-20 | Inference tuning | — | score=0.9392 | TTA + cls^0.7, sweep results above |

## Key Dataset Insights
- 328/356 categories have reference images (92% coverage)
- 35 categories have NO reference images
- 141 categories have ≤20 annotation crops (high-risk)
- 11 WASA knekkebrød variants differ only by weight text
- Average 92 boxes/image, up to 235
- 42% of boxes on image edges (truncation)
- Egg products are the most confusable family by far
