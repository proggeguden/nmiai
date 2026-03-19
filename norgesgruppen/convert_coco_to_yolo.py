"""Convert COCO annotations to YOLO format for single-class detection MVP."""

import json
import os
import random
from pathlib import Path

SEED = 42
TRAIN_RATIO = 0.9
DATA_DIR = Path(__file__).parent / "data"
COCO_DIR = DATA_DIR / "NM_NGD_coco_dataset"
YOLO_DIR = DATA_DIR / "yolo"


def main():
    with open(COCO_DIR / "annotations.json") as f:
        coco = json.load(f)

    # Build image lookup: id -> {file_name, width, height}
    images = {img["id"]: img for img in coco["images"]}

    # Group annotations by image_id
    anns_by_image = {}
    for ann in coco["annotations"]:
        anns_by_image.setdefault(ann["image_id"], []).append(ann)

    # Train/val split
    image_ids = sorted(images.keys())
    random.seed(SEED)
    random.shuffle(image_ids)
    split_idx = int(len(image_ids) * TRAIN_RATIO)
    splits = {
        "train": image_ids[:split_idx],
        "val": image_ids[split_idx:],
    }

    print(f"Total images: {len(image_ids)}")
    print(f"Train: {len(splits['train'])}, Val: {len(splits['val'])}")

    # Create directories and write labels
    for split_name, ids in splits.items():
        img_dir = YOLO_DIR / "images" / split_name
        lbl_dir = YOLO_DIR / "labels" / split_name
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        total_boxes = 0
        for img_id in ids:
            img_info = images[img_id]
            w_img, h_img = img_info["width"], img_info["height"]
            fname = img_info["file_name"]
            stem = Path(fname).stem

            # Symlink image
            src = COCO_DIR / "images" / fname
            dst = img_dir / fname
            if not dst.exists():
                os.symlink(src.resolve(), dst)

            # Write YOLO label (class x_center y_center w h — all normalized)
            anns = anns_by_image.get(img_id, [])
            lines = []
            for ann in anns:
                x, y, w, h = ann["bbox"]  # COCO: top-left x,y + width,height (absolute px)
                x_center = (x + w / 2) / w_img
                y_center = (y + h / 2) / h_img
                w_norm = w / w_img
                h_norm = h / h_img

                # Clamp to [0, 1]
                x_center = max(0.0, min(1.0, x_center))
                y_center = max(0.0, min(1.0, y_center))
                w_norm = max(0.0, min(1.0, w_norm))
                h_norm = max(0.0, min(1.0, h_norm))

                lines.append(f"0 {x_center:.6f} {y_center:.6f} {w_norm:.6f} {h_norm:.6f}")
                total_boxes += 1

            with open(lbl_dir / f"{stem}.txt", "w") as f:
                f.write("\n".join(lines))

        print(f"{split_name}: {len(ids)} images, {total_boxes} boxes")

    # Write dataset.yaml
    yaml_path = YOLO_DIR / "dataset.yaml"
    yaml_content = f"""path: {YOLO_DIR.resolve()}
train: images/train
val: images/val

nc: 1
names:
  0: product
"""
    with open(yaml_path, "w") as f:
        f.write(yaml_content)

    print(f"\nDataset YAML written to {yaml_path}")
    print("Done!")


if __name__ == "__main__":
    main()
