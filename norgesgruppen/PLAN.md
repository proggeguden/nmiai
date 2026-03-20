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

### 1. Letterbox Retraining + User Photos (expected +3-6%)
**The #1 improvement opportunity.** Two changes, done together:

**a) Retrain classifier with letterbox crops (preserving aspect ratio)**
- Currently crops are squashed to 260×260, destroying width/height info
- Egg 6-packs (363px wide) and 12-packs (675px wide) become identical squares
- Tested letterbox at inference: 6-pack AP improved +0.20, but 12-packs broke (−0.13)
  because classifier was trained on squashed crops → distribution mismatch
- **Fix: retrain with letterboxed crops from the start**
- Modify `extract_crops.py` to use letterbox (resize-with-pad) instead of squash
- Modify `train_classifier.py` augmentations to match
- Then enable `USE_LETTERBOX_CROPS = True` in run.py
- **On GCP VM**: re-extract crops → retrain classifier → re-export ONNX + embeddings

**b) Photograph products at the store**
- Priority: egg variants (6/10/12-pack), AP=0 categories, no-ref-image products
- See `shopping_list.txt` for full prioritized list
- See `data/viz/egg_reference/` to compare existing ref images vs shelf crops

**Photography tips (for tomorrow):**
- Photograph products ON THE SHELF, straight-on at eye level
- Use store lighting (no flash — causes packaging reflections)
- Take 2-3 shots per product at slightly different angles (±10-15°)
- For eggs: make sure the pack size number ("6 stk", "12 stk") is clearly readable
- For eggs: include a photo showing different pack sizes side by side on the shelf
- Phone camera is fine — matches the training data quality
- Focus on: egg variants > AP=0 categories > no-ref-image products > confusable pairs

**16 egg categories have NO reference images** (308 annotations total):
- Økologiske Egg 6/10stk, Eldorado variants, Galåvolden, Tørresvik, Sunnmørsegg, Leka
- Full list: see `data/viz/egg_reference/` folder for what exists vs what's missing
- Taking photos of these would directly fill a critical gap

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
- 18× EGG FRITTGÅENDE M/L 6PK ← EGG FRITTGÅENDE 12STK (Prior)
- 7× SOLEGG 6STK ← SOLEGG 12STK
- 3× EGG ØKOLOGISK ← FROKOSTEGG
- Various farm eggs confused (Galåvolden, Tørresvik, Leka)

**Root cause: aspect ratio destruction in crop preprocessing**
- 6-pack: ~363px wide × 183px tall → squashed to 260×260
- 12-pack: ~675px wide × 183px tall → squashed to 260×260
- Same height, same brand, same colors → indistinguishable after squashing
- Letterbox inference test: 6-pack AP +0.20, but 12-pack AP −0.13 (needs retraining)
- 16/30 egg categories have NO reference images → kNN can't help
- Browse: `data/viz/egg_reference/` — all egg ref images + annotated egg shelf

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
