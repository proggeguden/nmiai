# NorgesGruppen — Plan

## Phase 1: Detection MVP (in progress)
**Goal**: Single-class detection → up to 70% of competition score

- [x] Scaffold folder, .gitignore, CLAUDE.md
- [x] `convert_coco_to_yolo.py` — converts COCO annotations to YOLO format (all classes → 0)
- [x] `train.py` — YOLOv8m training script (imgsz=1280, heavy augmentation)
- [x] `run.py` — inference entry point for submission
- [x] `validate.py` — local mAP@0.5 evaluation with pycocotools
- [x] `package.py` — creates submission.zip
- [x] Provision GCP VM (nmiai-train, L4 GPU, europe-west4-a)
- [x] Upload data and start training
- [ ] **NEXT**: Wait for training to finish (~1-2 hours)
- [ ] Download `best.pt` from VM
- [ ] Run `validate.py` locally to verify mAP@0.5
- [ ] Run `package.py` to create submission.zip
- [ ] Submit at app.ainm.no
- [ ] Delete GCP VM

## Phase 2: Classification (future)
**Goal**: Multi-class detection → target remaining 30% of score

- [ ] Train multi-class YOLOv8 with all 356 categories
- [ ] Use product reference images (`NM_NGD_product_images/`) for few-shot augmentation
- [ ] Consider separate classifier on detected crops (two-stage approach)
- [ ] Explore: CLIP/DINOv2 embeddings + kNN on product reference images
- [ ] Tune confidence thresholds per-category

## Phase 3: Optimization (future)
- [ ] Test Tile Augmentation (SAHI) for small product detection
- [ ] Ensemble multiple model sizes (YOLOv8m + YOLOv8l)
- [ ] Test Time Augmentation (TTA) — multi-scale, flips
- [ ] Weighted Boxes Fusion (WBF) for ensemble merging
- [ ] Tune NMS/conf thresholds on validation set

## Training Log
| Date | Model | Epochs | Val mAP@0.5 | Notes |
|------|-------|--------|-------------|-------|
| 2026-03-19 | YOLOv8m | training... | 0.935 @ ep4 | MVP single-class, GCP L4 |
