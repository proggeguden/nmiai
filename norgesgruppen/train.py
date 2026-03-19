"""Train YOLOv8m for single-class product detection. Run on GCP GPU VM."""

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
        batch=8,
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
        name="detect_mvp",
        exist_ok=True,
        save=True,
        plots=True,
    )

    print("\nTraining complete!")
    print(f"Best weights: runs/detect_mvp/weights/best.pt")


if __name__ == "__main__":
    main()
