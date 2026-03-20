"""Train YOLOv8m for multi-class product detection. Run on GCP GPU VM.

IMPORTANT: Pin ultralytics==8.1.0 to match sandbox version.
    pip3 install ultralytics==8.1.0
"""

import torch
# Monkey-patch: ultralytics 8.1.0 doesn't pass weights_only=False,
# but torch 2.6.0 defaults to True. Fix for training only.
_original_torch_load = torch.load
torch.load = lambda *args, **kwargs: _original_torch_load(*args, **{**kwargs, 'weights_only': False})

from ultralytics import YOLO
from pathlib import Path

DATA_YAML = Path(__file__).parent / "data" / "yolo" / "dataset.yaml"


def main():
    model = YOLO("yolov8m.pt")  # pretrained COCO weights

    model.train(
        data=str(DATA_YAML),
        epochs=300,
        patience=50,
        imgsz=1280,
        batch=4,  # reduced from 8: 357 classes uses more VRAM
        device=0,
        # Augmentation — critical with only 248 images
        mosaic=1.0,
        mixup=0.15,
        copy_paste=0.1,
        scale=0.5,
        fliplr=0.5,
        flipud=0.0,  # no vertical flip — shelves don't flip
        erasing=0.3,
        # Training params
        lr0=0.01,
        lrf=0.01,
        warmup_epochs=5,
        cos_lr=True,
        # Output
        project="runs",
        name="multiclass",
        exist_ok=True,
        save=True,
        plots=True,
    )

    print("\nTraining complete!")
    print("Best weights: runs/multiclass/weights/best.pt")


if __name__ == "__main__":
    main()
