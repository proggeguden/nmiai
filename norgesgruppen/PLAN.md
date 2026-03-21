# NorgesGruppen — Competition Plan

## Current Score: 0.9215 (test, #6/319) / 0.9560 (local val) — Target: 0.9255 (#1)
- Detection mAP@0.5: 0.960 (× 0.7 = 0.672)
- Classification mAP@0.5: 0.941 (× 0.3 = 0.282)

## Completed

### Phase 1: Detection MVP ✅
- Multi-class YOLOv8m → mAP@0.5 = 0.816
- First working submission (ONNX, correct format)

### Phase 2: Two-Stage Pipeline ✅
- YOLOv8l single-class detector → mAP@0.5 = 0.967
- EfficientNet-B2 classifier → 90.8% val accuracy (356 classes)
- kNN embedding ensemble (24,308 embeddings, cosine similarity)
- Dual-output ONNX (logits + features in one forward pass)

### Phase 3: Diagnostics & Inference Tuning ✅
- Full competition validation: 70/30 scoring with per-class AP breakdown
- TTA (4 augments) + score=det×cls^0.7 → 0.9392

### Phase 4: WBF Ensemble ✅
- Multi-class YOLOv8m (mAP=0.829) + two-stage pipeline
- WBF fusion with weights 0.5/0.5 → improved test score

### Phase 5: Letterbox Classifier ✅ — THE BIG WIN
- **0.6840 → 0.9143 (+0.23!)** on test
- Letterbox preserves aspect ratio (critical for egg 6-pack vs 12-pack)
- EfficientNet-B2 letterbox-trained, val_acc=0.9291

### Phase 6: Overnight Models + Dual Backbone ✅
- Trained 3 models overnight: aggressive-aug (92.99%), ArcFace (92.78%), DINOv2 (93.16%)
- Built dual-backbone ONNX: EfficientNet-B2 + DINOv2-ViT-S (114.6 MB)
- DINOv2 ensemble (0.5/0.5) → 0.9158 on test (+0.0015)

### Phase 7: WBF Weight Tuning ✅ — RANK #7!
- **0.9158 → 0.9199 (+0.0041)** on test
- WBF weights 0.7/0.3 (favoring two-stage over multiclass YOLO)
- Parameter sweep found +0.013 locally; confirmed +0.004 on test
- Dual backbone + tuned WBF = **rank #7 out of 173 teams**

## Completed (2026-03-21 afternoon)

### Phase 8: DINOv2 kNN Activation ✅ — 0.9199 → 0.9206
- Discovered kNN was completely disabled in submissions (package.py excluded embeddings)
- Generated compact DINOv2 embeddings (384-dim, uint8 quantized, 11MB as JSON)
- Embedded in _knn_data.json to stay within 3 weight file limit
- Both WBF and kNN now active simultaneously

### Training Results
- **VM1**: Augmented detector — crashed on startup (wrong resume path), never trained
- **VM2**: DINOv2 v2 — 92.95%, no improvement over v1 (93.16%)
- **VM3**: EfficientNet-B4 — **93.03% val_acc** (done, slightly beats B2's 92.99%)

## Key Findings (2026-03-21 evening)

### Parameter Sweep (partial — with ensemble_boxes proper WBF)
| Config | Det mAP | Cls mAP | Score | vs baseline |
|--------|---------|---------|-------|-------------|
| current (knn=0.4) | 0.9605 | 0.9420 | 0.9550 | — |
| **knn=0.2** | **0.9607** | **0.9429** | **0.9554** | **+0.0004** |
| knn=0.3 | 0.9606 | 0.9430 | 0.9553 | +0.0003 |

### Data Analysis
- **Classification near-perfect locally**: 2057 correct, 21 confused, 44 missed
- **False positives are main issue**: 3116 preds vs 2122 GT (+47% excess)
- **unknown_product (cat 355)**: 67 preds vs 9 GT — 58 FPs, most low-confidence
- **ensemble_boxes WBF gives +0.0009** local val vs NMS fallback
- **Local val now matches sandbox** (both use ensemble_boxes)
- Dense images worst: img_00033 has 256 preds vs 161 GT
- At score threshold 0.25: only 86 excess preds (vs 994 at current threshold)

### Confusion Clusters (all 1x each — no systematic errors)
- WASA knekkebrød variants: 4 confusions (size/flavor mix-ups)
- Egg products: 3 confusions (6-pack vs 12-pack, organic vs regular)
- Each confusion is unique (never 2x same pair)

## Next Steps — 1 submission remaining today

### Available Resources
- **VM1** (nmiai-train): idle, has detector weights + data
- **VM3** (nmiai-train-arcface): idle, has B4 classifier (93.03%)
- **VM2** (nmiai-train-multiclass): idle, has multiclass YOLO weights + data

### Sweep Complete — Results
| Config | Score | vs baseline |
|--------|-------|-------------|
| **knn=0.1+wbf=0.8/0.2+dino=0.3** | **0.9560** | **+0.0019** (submitted, got 0.9215) |
| combo2 (knn=0.2+wbf=0.8/0.2) | 0.9557 | +0.0016 |
| knn=0.1 | 0.9556 | +0.0015 |
| knn=0.15 | 0.9555 | +0.0014 |
| combo1 (knn=0.2+dino=0.3) | 0.9554 | +0.0013 |
| dino=0.3 | 0.9549 | +0.0008 |
| wbf=0.8/0.2 | 0.9544 | +0.0003 |
| pow=0.8, dino=0.6 | 0.9541 | +0.0000 |
| pow=0.6 | 0.9540 | -0.0001 |

## Overnight Plan (2026-03-21 → 03-22)

### Gap Analysis: 0.9215 → 0.9255 (need +0.004)
- Detection 70% weight: +0.005 det_mAP → +0.0035 score (most leverage)
- Classification 30% weight: +0.013 cls_mAP → +0.004 score
- Val-test gap (0.035) driven by 134 unmeasured categories + FPs

### VM1 (nmiai-train): Copy-Paste Augmented Detector (~10h)
- Fix crash: generate augmented data first, then train
- `python3 copy_paste_augment.py --num-synthetic 750`
- `python3 train_detector.py --augmented --aggressive-aug`
- 4x more training data, rare class oversampling
- Expected: det_mAP 0.960 → 0.965+ → +0.0035 score
- Backup: `cp runs/detector_l/weights/best.pt best_v1_0.960.pt`

### VM2 (nmiai-train-multiclass): Better Multiclass YOLO (~12h)
- Current mAP=0.829 is weakest link in WBF
- Retrain YOLOv8m with aggressive augmentation (copy_paste=0.3, scale=0.7, color jitter)
- Expected: mAP 0.829 → 0.85+ → +0.001-0.003 score

### VM3 (nmiai-train-arcface): Full-Dataset Classifiers (~4h total)
- Add --full-train flag: train on all 248 images (no val holdout)
- Step 1: EfficientNet-B2 (--letterbox --aggressive-aug --full-train, 100 epochs, ~2.5h)
- Step 2: DINOv2-ViT-S (--letterbox --aggressive-aug --full-train, 50 epochs, ~1.5h)
- Then: build_dual_classifier.py + extract_dino_embeddings.py

### Local: Parameter Sweeps + Inference Fixes (tonight)
- Sweep WBF_SKIP_BOX_THRESH: {0.01, 0.03, 0.05, 0.10}
- Sweep KNN_K: {3, 5, 7, 10}
- Add MIN_FINAL_SCORE threshold to cut FPs
- Suppress low-confidence unknown_product (cat 355)

### Submission Strategy (5 submissions on 2026-03-22)
1. **Sub 1** (early): Current models + sweep-tuned thresholds only (safe)
2. **Sub 2**: New augmented detector (isolate detector gain)
3. **Sub 3**: + New multiclass YOLO (test WBF improvement)
4. **Sub 4**: + Full-data classifiers + new embeddings (aggressive)
5. **Sub 5**: Best combo from 1-4 + any refinements

## Exact Config for 0.9206 Submission (PROVEN — DO NOT BREAK)
- **detector.onnx**: YOLOv8l single-class (167MB) — original, unchanged
- **classifier.onnx**: Dual-backbone EfficientNet-B2 (letterbox v1) + DINOv2-ViT-S (114.6MB)
- **multiclass_detector.onnx**: YOLOv8m multi-class (100MB, mAP=0.829)
- **_knn_data.json**: DINOv2 kNN embeddings (384-dim, uint8 quantized, 11MB)
- **run.py settings**:
  - `USE_LETTERBOX_CROPS = True`
  - `USE_WBF = True`
  - `WBF_TWO_STAGE_WEIGHT = 0.7`, `WBF_MULTICLASS_WEIGHT = 0.3`
  - `SCORE_CLS_POWER = 0.7`
  - `DINO_WEIGHT = 0.5`
  - `KNN_WEIGHT = 0.4` (DINOv2 features for kNN)
  - `USE_TTA = True` (4 augments)
  - `DET_CONF = 0.10`
- Proven weights archived in `weights/`

## Available Scripts
| Script | Purpose | Flags |
|--------|---------|-------|
| `train_classifier.py` | EfficientNet classifier | `--letterbox`, `--arcface`, `--aggressive-aug`, `--model`, `--epochs`, `--batch-size` |
| `train_dino_classifier.py` | DINOv2-ViT-S | `--letterbox`, `--aggressive-aug` |
| `train_detector.py` | YOLOv8l single-class | `--augmented`, `--aggressive-aug` |
| `train_rtdetr.py` | RT-DETR-L transformer | `--augmented` |
| `copy_paste_augment.py` | Synthetic images | `--num-synthetic N` |
| `build_dual_classifier.py` | Merge EfficientNet + DINOv2 | — |
| `precompute_embeddings.py` | Export ONNX + kNN | `--letterbox`, `--arcface` |
| `fast_sweep.py` | Parameter sweep | — |

## GCP VMs
```bash
gcloud compute ssh nmiai-train --zone=europe-west4-a --project=ai-nm26osl-1788
gcloud compute ssh nmiai-train-arcface --zone=europe-west4-c --project=ai-nm26osl-1788
gcloud compute ssh nmiai-train-multiclass --zone=europe-west1-c --project=ai-nm26osl-1788

# Check training progress:
# VM1: tail ~/norgesgruppen/train_detector_aug.log
# VM3: tail ~/norgesgruppen/train_b4.log
# VM2: DONE (dino v2, val_acc=92.95%)
```

## Weight Budget
| File | Size | Purpose |
|------|------|---------|
| detector.onnx | 167MB | YOLOv8l single-class detection |
| classifier.onnx | 115MB | Dual-backbone: EfficientNet-B2 + DINOv2-ViT-S |
| multiclass_detector.onnx | 100MB | YOLOv8m multi-class for WBF |
| **Total** | **382MB** | < 420MB limit ✓ |

## Training Log
| Date | Model | Epochs | Metric | Notes |
|------|-------|--------|--------|-------|
| 03-20 | YOLOv8l (nc=1) | 54 | mAP=0.967 | detector, unchanged |
| 03-20 | EfficientNet-B2 (squash) | 80 | acc=90.8% | original classifier |
| 03-20 | YOLOv8m (nc=356) | 300 | mAP=0.829 | multiclass for WBF |
| 03-20 | EfficientNet-B2 (letterbox) | 80 | acc=92.91% | **scored 0.9143 on test** |
| 03-21 | EfficientNet-B2 (letterbox+arcface+aggaug) | 80 | acc=92.78% | ArcFace, done |
| 03-21 | EfficientNet-B2 (letterbox+aggaug) | 80 | acc=92.99% | aggressive-aug, done |
| 03-21 | DINOv2-ViT-S v1 (letterbox+aggaug) | 40 | acc=93.16% | **used in dual backbone** |
| 03-21 | DINOv2-ViT-S v2 (letterbox+aggaug) | 40 | acc=92.95% | retrain, no improvement |
| 03-21 | EfficientNet-B4 (letterbox+aggaug) | 120 | acc=93.03% | **done, ready to use** |
| 03-21 | YOLOv8l augmented (nc=1) | — | — | crashed on startup (wrong path) |

## Score History
| Date | Score | Rank | Config |
|------|-------|------|--------|
| 03-20 | 0.6775 | — | Two-stage + kNN |
| 03-20 | 0.6840 | — | + WBF, - kNN |
| 03-20 | 0.9143 | #13 | + Letterbox classifier |
| 03-21 | 0.9157 | — | Aggressive-aug EfficientNet-B2 (drop-in) |
| 03-21 | 0.9158 | — | Dual backbone (EfficientNet-B2 + DINOv2), WBF 0.5/0.5 |
| 03-21 | 0.9199 | #7 | Dual backbone + WBF 0.7/0.3 |
| 03-21 | 0.9206 | — | + DINOv2 kNN (was missing from previous submissions) |
| 03-21 | **0.9215** | **#6/319** | **+ Param sweep: knn=0.1, wbf=0.8/0.2, dino=0.3** |
