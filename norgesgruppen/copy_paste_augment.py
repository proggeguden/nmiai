"""Copy-paste augmentation: paste product crops onto shelf backgrounds.

Generates synthetic training images by:
1. Extracting product crops from existing annotations
2. Pasting them at random positions on shelf backgrounds
3. Focusing on rare categories (< 20 annotations) — pasted 10× more often

This directly addresses the long-tail problem (41 categories with 1 annotation,
158 with <20) by creating diverse synthetic scenes.

Usage:
    python3 extract_crops.py           # must have crops first
    python3 copy_paste_augment.py      # generates augmented YOLO dataset
    python3 train_detector.py          # retrain on augmented data
"""

import json
import random
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

DATA_DIR = Path(__file__).parent / "data"
COCO_DIR = DATA_DIR / "NM_NGD_coco_dataset"
YOLO_DIR = DATA_DIR / "yolo"
OUTPUT_DIR = DATA_DIR / "yolo_augmented"
CROPS_DIR = DATA_DIR / "crops"

NUM_SYNTHETIC = 750  # number of synthetic images to generate
PASTES_PER_IMAGE = (3, 6)  # random range of crops to paste per image
SCALE_JITTER = (0.7, 1.3)  # scale variation for pasted crops
RARE_THRESHOLD = 20  # categories with fewer annotations get oversampled
RARE_OVERSAMPLE = 10  # how much more often to sample rare categories
SEED = 42


def load_coco_data():
    """Load COCO annotations and build per-category crop info."""
    with open(COCO_DIR / "annotations.json") as f:
        coco = json.load(f)

    images = {img["id"]: img for img in coco["images"]}
    annotations = coco["annotations"]
    categories = {cat["id"]: cat["name"] for cat in coco["categories"]}

    # Count annotations per category
    cat_counts = Counter(ann["category_id"] for ann in annotations)

    return images, annotations, categories, cat_counts


def extract_crop_with_mask(img, bbox, pad_ratio=0.02):
    """Extract a tight crop from image. Returns (crop_pil, alpha_mask)."""
    w_img, h_img = img.size
    x, y, w, h = bbox

    # Tight crop with minimal padding
    px, py = w * pad_ratio, h * pad_ratio
    x1 = max(0, int(x - px))
    y1 = max(0, int(y - py))
    x2 = min(w_img, int(x + w + px))
    y2 = min(h_img, int(y + h + py))

    if x2 - x1 < 10 or y2 - y1 < 10:
        return None, None

    crop = img.crop((x1, y1, x2, y2))

    # Create alpha mask with feathered edges for blending
    cw, ch = crop.size
    alpha = Image.new("L", (cw, ch), 255)
    # Feather 3px edges
    feather = 3
    alpha_arr = np.array(alpha)
    for i in range(feather):
        val = int(255 * (i + 1) / (feather + 1))
        alpha_arr[i, :] = np.minimum(alpha_arr[i, :], val)
        alpha_arr[ch - 1 - i, :] = np.minimum(alpha_arr[ch - 1 - i, :], val)
        alpha_arr[:, i] = np.minimum(alpha_arr[:, i], val)
        alpha_arr[:, cw - 1 - i] = np.minimum(alpha_arr[:, cw - 1 - i], val)
    alpha = Image.fromarray(alpha_arr)

    return crop, alpha


def build_crop_pool(images, annotations, cat_counts):
    """Build pool of crops grouped by rarity. Returns list of (crop, alpha, cat_id, bbox_wh)."""
    pool = []
    img_cache = {}

    # Sort by image to minimize disk reads
    anns_by_img = {}
    for ann in annotations:
        anns_by_img.setdefault(ann["image_id"], []).append(ann)

    for img_id, anns in anns_by_img.items():
        img_info = images[img_id]
        img_path = COCO_DIR / "images" / img_info["file_name"]
        if not img_path.exists():
            continue

        img = Image.open(img_path).convert("RGB")

        for ann in anns:
            crop, alpha = extract_crop_with_mask(img, ann["bbox"])
            if crop is None:
                continue

            cat_id = ann["category_id"]
            pool.append({
                "crop": crop,
                "alpha": alpha,
                "category_id": cat_id,
                "is_rare": cat_counts[cat_id] < RARE_THRESHOLD,
                "bbox_wh": (ann["bbox"][2], ann["bbox"][3]),
            })

        img.close()

    print(f"Built crop pool: {len(pool)} crops")
    rare_count = sum(1 for p in pool if p["is_rare"])
    print(f"  Rare crops (<{RARE_THRESHOLD} annotations): {rare_count}")
    return pool


def build_weighted_pool(pool):
    """Create weighted sampling list favoring rare categories."""
    weighted = []
    for item in pool:
        weight = RARE_OVERSAMPLE if item["is_rare"] else 1
        weighted.extend([item] * weight)
    random.shuffle(weighted)
    print(f"Weighted pool size: {len(weighted)} (with rare oversampling)")
    return weighted


def get_background_images():
    """Get list of training images to use as backgrounds."""
    img_dir = COCO_DIR / "images"
    return sorted(img_dir.glob("*.jpg")) + sorted(img_dir.glob("*.png"))


def paste_crop_on_image(bg_img, crop_item, scale_factor):
    """Paste a crop onto background at a random shelf-plausible position."""
    crop = crop_item["crop"]
    alpha = crop_item["alpha"]

    # Scale the crop
    cw, ch = crop.size
    new_w = max(10, int(cw * scale_factor))
    new_h = max(10, int(ch * scale_factor))
    crop_scaled = crop.resize((new_w, new_h), Image.BILINEAR)
    alpha_scaled = alpha.resize((new_w, new_h), Image.BILINEAR)

    bg_w, bg_h = bg_img.size

    # Random position (prefer shelf-like positions: middle 80% vertically)
    max_x = bg_w - new_w
    max_y = bg_h - new_h
    if max_x <= 0 or max_y <= 0:
        return None  # crop too big for background

    paste_x = random.randint(0, max_x)
    # Vertical: prefer middle region (shelves are usually in middle)
    y_min = max(0, min(int(bg_h * 0.1), max_y))
    y_max = min(max_y, int(bg_h * 0.9))
    if y_max <= y_min:
        paste_y = random.randint(0, max_y)
    else:
        paste_y = random.randint(y_min, y_max)

    # Alpha-blend paste
    bg_img.paste(crop_scaled, (paste_x, paste_y), alpha_scaled)

    # Return the new bbox in COCO format [x, y, w, h]
    return [paste_x, paste_y, new_w, new_h]


def generate_synthetic_images(pool, bg_paths, num_images):
    """Generate synthetic training images with copy-paste augmentation."""
    weighted_pool = build_weighted_pool(pool)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    images_dir = OUTPUT_DIR / "images" / "train"
    labels_dir = OUTPUT_DIR / "labels" / "train"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    new_annotations = []
    ann_id_counter = 100000  # start high to avoid conflicts

    for i in range(num_images):
        # Pick random background
        bg_path = random.choice(bg_paths)
        bg_img = Image.open(bg_path).convert("RGB")
        bg_w, bg_h = bg_img.size

        # Pick number of crops to paste
        n_pastes = random.randint(*PASTES_PER_IMAGE)
        image_anns = []

        for _ in range(n_pastes):
            crop_item = random.choice(weighted_pool)
            scale = random.uniform(*SCALE_JITTER)

            bbox = paste_crop_on_image(bg_img, crop_item, scale)
            if bbox is None:
                continue

            image_anns.append({
                "category_id": crop_item["category_id"],
                "bbox": bbox,
            })

        if not image_anns:
            bg_img.close()
            continue

        # Save synthetic image
        out_name = f"synthetic_{i:05d}.jpg"
        bg_img.save(images_dir / out_name, quality=90)

        # Save YOLO-format labels
        label_name = f"synthetic_{i:05d}.txt"
        with open(labels_dir / label_name, "w") as f:
            for ann in image_anns:
                x, y, w, h = ann["bbox"]
                # Convert to YOLO format: cx, cy, w, h (normalized)
                cx = (x + w / 2) / bg_w
                cy = (y + h / 2) / bg_h
                nw = w / bg_w
                nh = h / bg_h
                # Single-class mode: class 0
                f.write(f"0 {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}\n")

        bg_img.close()

        if (i + 1) % 100 == 0:
            print(f"  Generated {i + 1}/{num_images} synthetic images")

    print(f"Generated {num_images} synthetic images in {images_dir}")
    return images_dir, labels_dir


def copy_original_data():
    """Copy original YOLO training data to augmented directory."""
    src_images = YOLO_DIR / "images" / "train"
    src_labels = YOLO_DIR / "labels" / "train"
    dst_images = OUTPUT_DIR / "images" / "train"
    dst_labels = OUTPUT_DIR / "labels" / "train"

    dst_images.mkdir(parents=True, exist_ok=True)
    dst_labels.mkdir(parents=True, exist_ok=True)

    count = 0
    if src_images.exists():
        for img_path in src_images.iterdir():
            if img_path.suffix.lower() in (".jpg", ".jpeg", ".png"):
                dst = dst_images / img_path.name
                if not dst.exists():
                    # Symlink to save disk space
                    dst.symlink_to(img_path.resolve())
                # Copy corresponding label
                label_name = img_path.stem + ".txt"
                src_label = src_labels / label_name
                dst_label = dst_labels / label_name
                if src_label.exists() and not dst_label.exists():
                    dst_label.symlink_to(src_label.resolve())
                count += 1

    # Also copy val data (unchanged)
    for split in ["val"]:
        src_img_split = YOLO_DIR / "images" / split
        src_lbl_split = YOLO_DIR / "labels" / split
        dst_img_split = OUTPUT_DIR / "images" / split
        dst_lbl_split = OUTPUT_DIR / "labels" / split

        if src_img_split.exists():
            dst_img_split.mkdir(parents=True, exist_ok=True)
            dst_lbl_split.mkdir(parents=True, exist_ok=True)
            for img_path in src_img_split.iterdir():
                dst = dst_img_split / img_path.name
                if not dst.exists():
                    dst.symlink_to(img_path.resolve())
                label_name = img_path.stem + ".txt"
                src_label = src_lbl_split / label_name
                dst_label = dst_lbl_split / label_name
                if src_label.exists() and not dst_label.exists():
                    dst_label.symlink_to(src_label.resolve())

    print(f"Linked {count} original training images")
    return count


def write_dataset_yaml(num_classes=1):
    """Write dataset.yaml for the augmented dataset."""
    yaml_content = f"""path: {OUTPUT_DIR.resolve()}
train: images/train
val: images/val

nc: {num_classes}
names: ['product']
"""
    yaml_path = OUTPUT_DIR / "dataset.yaml"
    with open(yaml_path, "w") as f:
        f.write(yaml_content)
    print(f"Dataset YAML written to {yaml_path}")
    return yaml_path


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-synthetic", type=int, default=NUM_SYNTHETIC,
                        help=f"Number of synthetic images to generate (default: {NUM_SYNTHETIC})")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    print("=== Copy-Paste Augmentation ===")
    print(f"Generating {args.num_synthetic} synthetic images\n")

    # Load data
    images, annotations, categories, cat_counts = load_coco_data()
    print(f"Categories: {len(categories)}, Annotations: {len(annotations)}")
    rare = sum(1 for c, n in cat_counts.items() if n < RARE_THRESHOLD)
    print(f"Rare categories (<{RARE_THRESHOLD} annotations): {rare}/{len(categories)}")

    # Build crop pool
    print("\nBuilding crop pool...")
    pool = build_crop_pool(images, annotations, cat_counts)

    # Get backgrounds
    bg_paths = get_background_images()
    print(f"Background images: {len(bg_paths)}")

    # Copy original data
    print("\nCopying original training data...")
    n_orig = copy_original_data()

    # Generate synthetic images
    print(f"\nGenerating {args.num_synthetic} synthetic images...")
    generate_synthetic_images(pool, bg_paths, args.num_synthetic)

    # Write dataset YAML
    print("\nWriting dataset config...")
    yaml_path = write_dataset_yaml()

    # Summary
    total_train = n_orig + args.num_synthetic
    print(f"\n=== Summary ===")
    print(f"Original training images: {n_orig}")
    print(f"Synthetic images:         {args.num_synthetic}")
    print(f"Total training images:    {total_train}")
    print(f"\nDataset ready at: {OUTPUT_DIR}")
    print(f"To train detector on augmented data:")
    print(f"  python3 train_detector.py --augmented")


if __name__ == "__main__":
    main()
