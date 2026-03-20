"""Train RT-DETR-L transformer-based detector. Run on GCP GPU VM.

RT-DETR provides architectural diversity vs YOLO — handles dense scenes
differently with attention-based detection. Useful as ensemble member.

Setup:
    pip3 install ultralytics==8.1.0
    pip3 install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
    python3 convert_coco_to_yolo.py --single_class
    python3 train_rtdetr.py
"""

import torch
_orig = torch.load
torch.load = lambda *a, **kw: _orig(*a, **{**kw, 'weights_only': False})

from ultralytics import YOLO
from pathlib import Path

DATA_YAML = Path(__file__).parent / "data" / "yolo" / "dataset.yaml"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--augmented", action="store_true",
                        help="Use copy-paste augmented dataset")
    args = parser.parse_args()

    data_yaml = DATA_YAML
    if args.augmented:
        aug_yaml = Path(__file__).parent / "data" / "yolo_augmented" / "dataset.yaml"
        if aug_yaml.exists():
            data_yaml = aug_yaml

    print(f"Dataset: {data_yaml}")

    model = YOLO("rtdetr-l.pt")

    model.train(
        data=str(data_yaml),
        epochs=200,
        patience=40,
        imgsz=1280,
        batch=2,
        device=0,
        # RT-DETR augmentation
        mosaic=1.0,
        mixup=0.1,
        scale=0.5,
        fliplr=0.5,
        # Training params
        lr0=0.0001,
        lrf=0.01,
        warmup_epochs=5,
        cos_lr=True,
        # Output
        project="runs",
        name="rtdetr_l",
        exist_ok=True,
        save=True,
        plots=True,
    )

    print("\nTraining complete!")
    print("Best weights: runs/rtdetr_l/weights/best.pt")
    print("\nTo export:")
    print("  from ultralytics import YOLO")
    print('  model = YOLO("runs/rtdetr_l/weights/best.pt")')
    print('  model.export(format="onnx", imgsz=1280, opset=17)')


if __name__ == "__main__":
    main()
