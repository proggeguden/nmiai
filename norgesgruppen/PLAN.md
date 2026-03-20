# NorgesGruppen — Competition Plan

## Current Score: 0.9143 (test, rank #13) / 0.9408 (local val)
- Detection mAP@0.5: 0.949 (× 0.7 = 0.664)
- Classification mAP@0.5: 0.922 (× 0.3 = 0.277)

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
- Proven weights archived: `weights/classifier_letterbox_v1_0.9143.onnx`

## In Progress (Training Overnight 2026-03-20)

### VM1: Aggressive-Aug Letterbox Classifier
- `nmiai-train` (europe-west4-a, g2-standard-16, L4)
- `python3 train_classifier.py --letterbox --aggressive-aug`
- Same proven architecture, but with stronger augmentation for domain robustness
- ColorJitter 0.5/0.5/0.4/0.1, GaussianBlur, RandomPosterize, RandomGrayscale
- Starting epoch 1/80

### VM3: ArcFace Letterbox Classifier
- `nmiai-train-arcface` (europe-west4-c, g2-standard-16, L4)
- `python3 train_classifier.py --letterbox --arcface --aggressive-aug`
- ArcFace angular margin loss for tighter clusters (helps confusable products)
- 512-dim embeddings, margin=0.5, scale=64
- Epoch 32/80, val_acc=0.9204

### VM2: DINOv2 Classifier
- `nmiai-train-multiclass` (europe-west1-c, g2-standard-8, L4)
- `python3 train_dino_classifier.py --letterbox --aggressive-aug`
- DINOv2-ViT-S — self-supervised features, inherently robust to distribution shift
- 40 epochs (5 head-only freeze + 35 full fine-tune), img_size=252 (14×18)
- Epoch 3/40, val_acc=0.82 (head-only phase, converging fast)

## Tomorrow's Plan

### 1. Evaluate overnight training results
- Download all 3 trained models from VMs
- Export each to ONNX with `precompute_embeddings.py`
- Test each locally with `validate.py`
- Compare: aggressive-aug vs ArcFace vs DINOv2 vs current best

### 2. Submit best model(s)
- If aggressive-aug wins: simple drop-in replacement for classifier.onnx
- If ArcFace wins: also gets better kNN embeddings (512-dim)
- If DINOv2 wins: build dual-backbone ONNX with `build_dual_classifier.py`
- Can also try combining: e.g. ArcFace classifier + DINOv2 as dual-backbone

### 3. Copy-paste augmentation (if time)
- `copy_paste_augment.py` — generates 750 synthetic training images
- Bug fixed (randint edge case), ready to run
- Retrain detector on augmented dataset: `train_detector.py --augmented --aggressive-aug`
- Long training (~4h for 300 epochs) — start on a VM early

### 4. User photos from store
- Shopping list ready (`shopping_list.txt`)
- Priority: egg variants, AP=0 categories, no-ref-image products
- `add_photos.py` → integrate → retrain

## Available Scripts
| Script | Purpose | Flags |
|--------|---------|-------|
| `train_classifier.py` | EfficientNet-B2 | `--letterbox`, `--arcface`, `--aggressive-aug` |
| `train_dino_classifier.py` | DINOv2-ViT-S | `--letterbox`, `--aggressive-aug` |
| `train_detector.py` | YOLOv8l single-class | `--augmented`, `--aggressive-aug` |
| `train_rtdetr.py` | RT-DETR-L transformer | `--augmented` |
| `copy_paste_augment.py` | Synthetic images | `--num-synthetic N` |
| `build_dual_classifier.py` | Merge EfficientNet + DINOv2 | — |
| `precompute_embeddings.py` | Export ONNX + kNN | `--letterbox`, `--arcface` |

## GCP VMs (DELETE WHEN DONE!)
```bash
gcloud compute ssh nmiai-train --zone=europe-west4-a --project=ai-nm26osl-1788
gcloud compute ssh nmiai-train-arcface --zone=europe-west4-c --project=ai-nm26osl-1788
gcloud compute ssh nmiai-train-multiclass --zone=europe-west1-c --project=ai-nm26osl-1788

# Check training progress:
# VM1: tail ~/norgesgruppen/train_aggressive.log
# VM3: tail ~/norgesgruppen/train_arcface.log
# VM2: tail ~/norgesgruppen/train_dino.log

# Backup before overwriting:
# cp runs/classifier/best.pt runs/classifier/best_{name}_{val_acc}.pt

# DELETE when done:
gcloud compute instances delete nmiai-train --zone=europe-west4-a --project=ai-nm26osl-1788
gcloud compute instances delete nmiai-train-arcface --zone=europe-west4-c --project=ai-nm26osl-1788
gcloud compute instances delete nmiai-train-multiclass --zone=europe-west1-c --project=ai-nm26osl-1788
```

## Weight Budget
| File | Size | Purpose |
|------|------|---------|
| detector.onnx | 167MB | YOLOv8l single-class detection |
| classifier.onnx | 31-117MB | EfficientNet-B2 (or dual-backbone with DINOv2) |
| multiclass_detector.onnx | 100MB | YOLOv8m multi-class for WBF |
| **Total** | **298-384MB** | < 420MB limit ✓ |

## Training Log
| Date | Model | Epochs | Metric | Notes |
|------|-------|--------|--------|-------|
| 03-20 | YOLOv8l (nc=1) | 54 | mAP=0.967 | detector, unchanged |
| 03-20 | EfficientNet-B2 (squash) | 80 | acc=90.8% | original classifier |
| 03-20 | YOLOv8m (nc=356) | 300 | mAP=0.829 | multiclass for WBF |
| 03-20 | EfficientNet-B2 (letterbox) | 80 | acc=92.91% | **scored 0.9143 on test** |
| 03-20 | EfficientNet-B2 (letterbox+arcface+aggaug) | 32/80 | acc=92.04% | training overnight |
| 03-20 | EfficientNet-B2 (letterbox+aggaug) | 1/80 | — | training overnight |
| 03-20 | DINOv2-ViT-S (letterbox+aggaug) | 3/40 | acc=82% | training overnight |

## Score History
| Date | Score | Rank | Config |
|------|-------|------|--------|
| 03-20 | 0.6775 | — | Two-stage + kNN |
| 03-20 | 0.6840 | — | + WBF, - kNN |
| 03-20 | **0.9143** | **#13** | + Letterbox classifier |
