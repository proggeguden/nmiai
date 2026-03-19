"""Inference entry point for submission. Detects products on shelf images."""

import argparse
import json
from pathlib import Path
from ultralytics import YOLO

MODEL_PATH = Path(__file__).parent / "best.pt"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", required=True, help="Path to images directory")
    parser.add_argument("--output", required=True, help="Path to output predictions JSON")
    args = parser.parse_args()

    model = YOLO(str(MODEL_PATH))
    images_dir = Path(args.images)
    image_files = sorted(images_dir.glob("*.jpg"))

    if not image_files:
        image_files = sorted(images_dir.glob("*.png"))

    print(f"Found {len(image_files)} images in {images_dir}")

    results_list = []
    for img_path in image_files:
        results = model.predict(
            source=str(img_path),
            imgsz=1280,
            conf=0.15,
            max_det=500,
            verbose=False,
        )

        predictions = []
        for r in results:
            boxes = r.boxes
            for i in range(len(boxes)):
                x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                conf = boxes.conf[i].item()
                # Convert xyxy to COCO [x, y, w, h] (top-left + size, absolute pixels)
                bbox = [
                    round(x1, 2),
                    round(y1, 2),
                    round(x2 - x1, 2),
                    round(y2 - y1, 2),
                ]
                predictions.append({
                    "bbox": bbox,
                    "category_id": 0,
                    "confidence": round(conf, 4),
                })

        results_list.append({
            "image_id": img_path.name,
            "predictions": predictions,
        })
        print(f"  {img_path.name}: {len(predictions)} detections")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results_list, f, indent=2)

    total = sum(len(r["predictions"]) for r in results_list)
    print(f"\nTotal: {total} detections across {len(results_list)} images")
    print(f"Output written to {output_path}")


if __name__ == "__main__":
    main()
