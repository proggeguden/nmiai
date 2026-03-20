"""Inference entry point for submission. Detects products on shelf images."""

import argparse
import json
import re
from pathlib import Path
from ultralytics import YOLO

MODEL_PATH = Path(__file__).parent / "model.onnx"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to images directory")
    parser.add_argument("--output", required=True, help="Path to output predictions JSON")
    args = parser.parse_args()

    model = YOLO(str(MODEL_PATH), task="detect")
    images_dir = Path(args.input)
    image_files = sorted(images_dir.glob("*.jpg"))

    if not image_files:
        image_files = sorted(images_dir.glob("*.png"))

    predictions = []
    for img_path in image_files:
        # Extract numeric image_id from filename: img_00042.jpg -> 42
        match = re.search(r"(\d+)", img_path.stem)
        image_id = int(match.group(1)) if match else 0

        results = model.predict(
            source=str(img_path),
            imgsz=1280,
            conf=0.15,
            max_det=500,
            verbose=False,
        )

        for r in results:
            boxes = r.boxes
            for i in range(len(boxes)):
                x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                score = boxes.conf[i].item()
                cls = int(boxes.cls[i].item())
                predictions.append({
                    "image_id": image_id,
                    "category_id": cls,
                    "bbox": [
                        round(x1, 2),
                        round(y1, 2),
                        round(x2 - x1, 2),
                        round(y2 - y1, 2),
                    ],
                    "score": round(score, 4),
                })

    output_path = Path(args.output)
    with open(output_path, "w") as f:
        json.dump(predictions, f)


if __name__ == "__main__":
    main()
