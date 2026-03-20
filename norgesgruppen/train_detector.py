"""Train YOLOv8l single-class detector. Run on GCP GPU VM.

Setup:
    pip3 install ultralytics==8.1.0
    pip3 install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
    python3 convert_coco_to_yolo.py --single_class
    python3 train_detector.py
"""

import torch
_orig = torch.load
torch.load = lambda *a, **kw: _orig(*a, **{**kw, 'weights_only': False})

from ultralytics import YOLO
from pathlib import Path

DATA_YAML = Path(__file__).parent / "data" / "yolo" / "dataset.yaml"


def main():
    model = YOLO("yolov8l.pt")

    model.train(
        data=str(DATA_YAML),
        epochs=300,
        patience=50,
        imgsz=1280,
        batch=4,
        device=0,
        # Augmentation
        mosaic=1.0,
        mixup=0.15,
        copy_paste=0.1,
        scale=0.5,
        fliplr=0.5,
        flipud=0.0,
        erasing=0.3,
        # Training params
        lr0=0.01,
        lrf=0.01,
        warmup_epochs=5,
        cos_lr=True,
        # Output
        project="runs",
        name="detector_l",
        exist_ok=True,
        save=True,
        plots=True,
    )

    print("\nTraining complete!")
    print("Best weights: runs/detector_l/weights/best.pt")


if __name__ == "__main__":
    main()
