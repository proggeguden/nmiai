# NorgesGruppen — Plan

## Phase 1: Detection MVP (DONE)
**Goal**: Single-class detection → up to 70% of competition score

- [x] Scaffold folder, .gitignore, CLAUDE.md
- [x] `convert_coco_to_yolo.py` — converts COCO annotations to YOLO format
- [x] `train.py` — YOLOv8m training script (imgsz=1280, heavy augmentation)
- [x] `run.py` — inference entry point for submission
- [x] `validate.py` — local mAP@0.5 evaluation with pycocotools
- [x] `package.py` — creates submission.zip
- [x] Provision GCP VM (nmiai-train, L4 GPU, europe-west4-a)
- [x] Single-class training complete (mAP@0.5=0.971 at epoch 46/96)

## Phase 2: Multi-class + Submission Fix (in progress)
**Goal**: Full detection + classification → 100% of competition score

- [x] Fix `run.py` bugs (--input, flat output, int image_id, score field, category_id)
- [x] Fix `convert_coco_to_yolo.py` for multi-class (preserve category IDs, nc=356)
- [x] Update `train.py` for multi-class (batch=4, pin ultralytics==8.1.0)
- [x] Pin ultralytics==8.1.0 + torch==2.6.0 on GCP VM
- [x] Start multi-class training on GCP VM
- [ ] **NEXT**: Wait for training to finish
- [ ] Download `best.pt` from VM
- [ ] Run `validate.py` locally to verify mAP
- [ ] Run `package.py` to create submission.zip
- [ ] Submit at app.ainm.no
- [ ] Delete GCP VM

## Phase 3: Optimization (future)
- [ ] Test Tile Augmentation (SAHI) for small product detection
- [ ] Ensemble multiple model sizes (YOLOv8m + YOLOv8l)
- [ ] Test Time Augmentation (TTA) — multi-scale, flips
- [ ] Weighted Boxes Fusion (WBF) for ensemble merging
- [ ] Tune NMS/conf thresholds on validation set
- [ ] Use product reference images for few-shot augmentation
- [ ] CLIP/DINOv2 embeddings + kNN for classification boost

## Training Log
| Date | Model | Epochs | Val mAP@0.5 | Notes |
|------|-------|--------|-------------|-------|
| 2026-03-19 | YOLOv8m | 96 (best@46) | 0.971 | Single-class, ultralytics 8.4.24 (incompatible) |
| 2026-03-20 | YOLOv8m | training... | TBD | Multi-class (356), ultralytics 8.1.0, torch 2.6.0 |
