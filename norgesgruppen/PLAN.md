# NorgesGruppen — Competition Plan

## Current Score: 0.9199 (test, rank #7 / 173 teams) / 0.9541 (local val)
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

## In Progress (Training 2026-03-21)

### VM1: Copy-Paste Augmented Detector
- `nmiai-train` (europe-west4-a, g2-standard-16, L4)
- `python3 train_detector.py --augmented --aggressive-aug`
- 750 synthetic images via copy-paste augmentation (rare class 10× oversampling)
- Epoch 53/300, mAP50=0.905 (current best detector: 0.967)
- ETA: ~3 hours
- `tail ~/norgesgruppen/train_detector_aug.log`

### VM3: EfficientNet-B4 Classifier
- `nmiai-train-arcface` (europe-west4-c, g2-standard-16, L4)
- `python3 train_classifier.py --letterbox --aggressive-aug --model efficientnet_b4 --epochs 120 --batch-size 64`
- Bigger model capacity than B2, more epochs
- Epoch 33/120, val_acc=91.58% (still converging, B2 best was 92.99%)
- ETA: ~3 hours
- `tail ~/norgesgruppen/train_b4.log`

### VM2: DINOv2 v2 — DONE
- Best val_acc=92.95% (slightly below v1's 93.16%)
- Not an improvement; keep using v1 in dual backbone

## Next Steps (when training finishes)

### 1. Evaluate new detector
- Download augmented detector from VM1
- Test with current best classifier (dual backbone)
- If mAP > 0.967: big potential gain (70% of score!)
- Package: new detector.onnx + existing classifier.onnx + multiclass_detector.onnx

### 2. Evaluate B4 classifier
- Download from VM3, export to ONNX
- Build dual-backbone with B4 instead of B2 (if B4 > B2 val_acc)
- Or try B4 standalone if it beats B2 by enough

### 3. Combine best of everything
- Best detector (original or augmented) + best classifier (B2 or B4 dual) + tuned WBF
- 3 submissions remaining today

### 4. Further training (if time)
- Copy-paste augmented multiclass YOLO (improve WBF partner)
- Even bigger classifier (B5? ConvNeXt?)
- User photos from store (`shopping_list.txt` ready)

## Exact Config for 0.9199 Submission (PROVEN — DO NOT BREAK)
- **detector.onnx**: YOLOv8l single-class (167MB) — original, unchanged
- **classifier.onnx**: Dual-backbone EfficientNet-B2 (letterbox v1) + DINOv2-ViT-S (114.6MB)
- **multiclass_detector.onnx**: YOLOv8m multi-class (100MB, mAP=0.829)
- **run.py settings**:
  - `USE_LETTERBOX_CROPS = True`
  - `USE_WBF = True`
  - `WBF_TWO_STAGE_WEIGHT = 0.7`, `WBF_MULTICLASS_WEIGHT = 0.3`
  - `SCORE_CLS_POWER = 0.7`
  - `DINO_WEIGHT = 0.5`
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
| 03-21 | EfficientNet-B4 (letterbox+aggaug) | 33/120 | acc=91.58% | training... |
| 03-21 | YOLOv8l augmented (nc=1) | 53/300 | mAP=0.905 | training... |

## Score History
| Date | Score | Rank | Config |
|------|-------|------|--------|
| 03-20 | 0.6775 | — | Two-stage + kNN |
| 03-20 | 0.6840 | — | + WBF, - kNN |
| 03-20 | 0.9143 | #13 | + Letterbox classifier |
| 03-21 | 0.9157 | — | Aggressive-aug EfficientNet-B2 (drop-in) |
| 03-21 | 0.9158 | — | Dual backbone (EfficientNet-B2 + DINOv2), WBF 0.5/0.5 |
| 03-21 | **0.9199** | **#7** | **Dual backbone + WBF 0.7/0.3** |
