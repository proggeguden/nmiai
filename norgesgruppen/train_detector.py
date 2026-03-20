"""Train YOLOv8l single-class detector. Run on GCP GPU VM.

Setup:
    pip3 install ultralytics==8.1.0
    pip3 install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
    python3 convert_coco_to_yolo.py --single_class
    python3 train_detector.py [--augmented] [--aggressive-aug]
"""

import torch
_orig = torch.load
torch.load = lambda *a, **kw: _orig(*a, **{**kw, 'weights_only': False})

from ultralytics import YOLO
from pathlib import Path

DATA_YAML = Path(__file__).parent / "data" / "yolo" / "dataset.yaml"
AUGMENTED_DATA_YAML = Path(__file__).parent / "data" / "yolo_augmented" / "dataset.yaml"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--augmented", action="store_true",
                        help="Use copy-paste augmented dataset (run copy_paste_augment.py first)")
    parser.add_argument("--aggressive-aug", action="store_true",
                        help="Use aggressive color/scale augmentation for domain robustness")
    args = parser.parse_args()

    data_yaml = AUGMENTED_DATA_YAML if args.augmented else DATA_YAML
    if args.augmented and not AUGMENTED_DATA_YAML.exists():
        print(f"Error: {AUGMENTED_DATA_YAML} not found. Run copy_paste_augment.py first!")
        return

    print(f"Dataset: {data_yaml}")

    model = YOLO("yolov8l.pt")

    # Augmentation params
    if args.aggressive_aug:
        print("Using AGGRESSIVE augmentation")
        aug_params = dict(
            copy_paste=0.3,
            scale=0.7,
            hsv_h=0.02,
            hsv_s=0.8,
            hsv_v=0.5,
        )
    else:
        aug_params = dict(
            copy_paste=0.1,
            scale=0.5,
        )

    model.train(
        data=str(data_yaml),
        epochs=300,
        patience=50,
        imgsz=1280,
        batch=2,
        device=0,
        # Augmentation
        mosaic=1.0,
        mixup=0.15,
        fliplr=0.5,
        flipud=0.0,
        erasing=0.3,
        **aug_params,
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
