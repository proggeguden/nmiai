# NorgesGruppen Data — Final Solution

**Final private score: 0.7095 mAP (#5) | Public score: 0.9216 (#11 / 350 teams)**

## Task

Detect and classify grocery products on store shelf images. Score = 0.7 × detection mAP@0.5 + 0.3 × classification mAP@0.5, across 356 product categories.

## Architecture

Two-stage detection-classification pipeline with WBF ensemble:

```
Image (variable resolution)
  │
  ├─► YOLOv8l single-class detector (1280px)
  │     → bounding boxes + detection confidence
  │     → crop each box (5% padding, letterbox resize to 260×260)
  │     → TTA: 4 variants (original, hflip, ±5° rotation)
  │     → Dual-backbone classifier (EfficientNet-B2 + DINOv2-ViT-S)
  │       → softmax ensemble: 0.7 × EfficientNet + 0.3 × DINOv2
  │       → kNN retrieval: 0.9 × classifier + 0.1 × kNN vote
  │     → score = det_conf × cls_conf^0.7
  │
  ├─► YOLOv8m multi-class detector (1280px, 356 classes)
  │     → bounding boxes + class + confidence
  │
  └─► Weighted Boxes Fusion (ensemble_boxes library)
        weights: 0.8 × two-stage, 0.2 × multi-class
        IoU threshold: 0.5
        → final predictions
        → suppress low-confidence unknown_product (cat 355): score -= 0.3
```

## Models

| Model | Architecture | Training | Val Metric |
|-------|-------------|----------|------------|
| **detector.onnx** (167 MB) | YOLOv8l, nc=1 | 54 epochs, imgsz=1280, 223 images | mAP@0.5 = 0.967 |
| **classifier.onnx** (115 MB) | EfficientNet-B2 + DINOv2-ViT-S (dual ONNX, 4 outputs) | 80 + 40 epochs, letterbox 260×260, aggressive augmentation | acc = 92.99% (B2), 93.16% (DINOv2) |
| **multiclass_detector.onnx** (100 MB) | YOLOv8m, nc=356 | 300 epochs, imgsz=1280, 223 images | mAP@0.5 = 0.829 |
| **_knn_data.json** (11 MB) | DINOv2 384-dim embeddings, uint8 quantized, zlib+base64 | Extracted from all training crops | ~2800 embeddings across 356 categories |

**Total weight budget: 392 MB / 420 MB limit (3 ONNX files + 1 JSON)**

## How to Reproduce

### Prerequisites

```bash
# Python packages (match sandbox versions exactly)
pip install ultralytics==8.1.0 timm==0.9.12 onnxruntime-gpu
pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
pip install ensemble-boxes pycocotools

# On headless VM
sudo apt-get install libgl1-mesa-glx libglib2.0-0
```

### Dataset Setup

Place competition data in `data/`:
```
norgesgruppen/data/
├── NM_NGD_coco_dataset/
│   ├── annotations.json    # COCO format, 248 images, 22731 annotations
│   └── images/             # img_00001.jpg ... img_00248.jpg
└── NM_NGD_product_images/  # 345 product reference folders (barcode-named)
    ├── 7035620058004/      # 5-7 reference photos per product
    └── ...
```

### Step 1: Prepare YOLO Data

```bash
# Convert COCO → YOLO format (single-class for detector)
python3 convert_coco_to_yolo.py --single_class
# Output: data/yolo/ with 223 train + 25 val images (90/10, seed=42)
```

### Step 2: Train Detector

```bash
# YOLOv8l single-class detector (requires GPU, ~3 hours on L4)
python3 train_detector.py
# Output: runs/detector_l/weights/best.pt
# Export: done automatically by ultralytics → best.onnx
# Copy to: detector.onnx
```

### Step 3: Extract Crops

```bash
# Crop annotations + map reference images via metadata.json
python3 extract_crops.py
# Output: data/crops/ with manifest.json (~2800 crops across 356 categories)
```

### Step 4: Train Classifiers

```bash
# EfficientNet-B2 with letterbox + aggressive augmentation (~2.5 hours on L4)
python3 train_classifier.py --letterbox --aggressive-aug
# Output: runs/classifier/best.pt (val_acc ~92.99%)

# DINOv2-ViT-S with letterbox + aggressive augmentation (~1.5 hours on L4)
python3 train_dino_classifier.py --letterbox --aggressive-aug
# Output: runs/dino_classifier/best.pt (val_acc ~93.16%)
```

### Step 5: Build Dual Classifier + Embeddings

```bash
# Merge both classifiers into single ONNX (4 outputs) + precompute kNN embeddings
python3 build_dual_classifier.py
# Output: classifier.onnx (115 MB), embeddings.npy (33 MB)
```

### Step 6: Train Multi-Class Detector

```bash
# Convert COCO → YOLO format (multi-class, 356 categories)
python3 convert_coco_to_yolo.py
# Train YOLOv8m multi-class (~12 hours on L4)
python3 train.py
# Output: runs/multiclass/weights/best.pt → export to multiclass_detector.onnx
```

### Step 7: Prepare kNN Data

The `build_dual_classifier.py` outputs `embeddings.npy` (float32, ~33 MB). For submission, this is converted to `_knn_data.json` (uint8 quantized, zlib + base64 compressed, ~11 MB) to fit within the 3-file weight limit.

`run.py` loads whichever format is available: `_knn_data.json` first, then `embeddings.npy`, then gracefully degrades to classifier-only mode.

### Step 8: Validate Locally

```bash
# Full competition scoring on val split (25 images)
python3 validate.py
# Expected: Det mAP ~0.961, Cls mAP ~0.944, Score ~0.956
```

### Step 9: Package and Submit

```bash
python3 package.py
# Output: submission.zip (~334 MB compressed, 392 MB uncompressed)
# Upload to app.ainm.no
```

## Best Submission Config (run.py)

These are the exact parameters that scored 0.9216:

```python
DET_CONF = 0.10              # detection confidence threshold
DET_IOU = 0.5                # NMS IoU threshold
DET_IMGSZ = 1280             # detector input size
DET_MAX_DET = 500            # max detections per image

USE_WBF = True               # enable Weighted Boxes Fusion
WBF_TWO_STAGE_WEIGHT = 0.8   # two-stage pipeline weight in WBF
WBF_MULTICLASS_WEIGHT = 0.2  # multi-class YOLO weight in WBF
WBF_IOU_THRESH = 0.5         # WBF merge threshold
WBF_SKIP_BOX_THRESH = 0.01   # WBF minimum score

USE_LETTERBOX_CROPS = True   # preserve aspect ratio in crops
PAD_RATIO = 0.05             # padding around detection boxes
CLS_IMGSZ = 260              # classifier input size

USE_TTA = True               # test-time augmentation (4 variants)
SCORE_CLS_POWER = 0.7        # score = det_conf × cls_conf^0.7
DINO_WEIGHT = 0.3            # 0.7 × EfficientNet + 0.3 × DINOv2
KNN_WEIGHT = 0.1             # 0.9 × classifier + 0.1 × kNN

UNKNOWN_SCORE_BOOST = 0.3    # suppress low-confidence cat 355 predictions
```

## Key Decisions and What Worked

| Change | Impact | Notes |
|--------|--------|-------|
| **Letterbox crops** | +0.230 | Single biggest win. Preserves aspect ratio — critical for egg 6-pack vs 12-pack |
| **Dual backbone (B2 + DINOv2)** | +0.002 | DINOv2 features are more robust, complementary to EfficientNet |
| **WBF ensemble** | +0.004 | Fusing two-stage + multi-class catches boxes each pipeline misses |
| **DINOv2 kNN retrieval** | +0.001 | Non-parametric backup for rare categories (84 have ≤5 annotations) |
| **Parameter sweep** | +0.001 | Optimized kNN/WBF/DINOv2 weights: less is more (kNN 0.4→0.1, dino 0.5→0.3) |
| **Unknown product suppression** | +0.0001 | Cat 355 had 58 FPs; subtracting 0.3 from score removes most |

## What Didn't Work

| Attempt | Result | Lesson |
|---------|--------|--------|
| Full-dataset training (no val holdout) | Flat on test | Disabling kNN to avoid feature mismatch negated the data gain |
| Copy-paste augmented detector | mAP dropped 0.967→0.950 | Aggressive augmentation introduced artifacts |
| Cross-class NMS after WBF | -0.003 on test | Removed predictions that were TPs for unmeasured categories |
| Scale TTA (replacing rotation) | Hurt on test | Rotation TTA was better despite seeming useless for shelves |
| MIN_FINAL_SCORE threshold | Hurt locally | mAP is insensitive to low-score FP removal due to P-R interpolation |
| Multiclass YOLO retraining | Flat (0.827 vs 0.829) | Aggressive augmentation didn't help multi-class YOLO |

## Score Progression

| Date | Score | Rank | Key Change |
|------|-------|------|------------|
| 03-20 | 0.6775 | — | Two-stage pipeline (squashed crops) |
| 03-20 | 0.6840 | — | + WBF ensemble |
| 03-20 | 0.9143 | #13 | + Letterbox classifier (+0.230!) |
| 03-21 | 0.9158 | — | + Dual backbone (EfficientNet-B2 + DINOv2) |
| 03-21 | 0.9199 | #7 | + WBF weight tuning (0.7/0.3) |
| 03-21 | 0.9206 | — | + DINOv2 kNN activated (was broken in packaging) |
| 03-21 | 0.9215 | #6 | + Parameter sweep optimization |
| 03-22 | **0.9216** | **#11** | + Unknown product suppression |
