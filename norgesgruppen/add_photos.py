"""Integrate user-taken photos into the training pipeline.

Place photos in data/user_photos/{category_id}/ then run this script.

Usage:
    python3 add_photos.py                    # process all user photos
    python3 add_photos.py --category 213     # process specific category only
    python3 add_photos.py --dry-run          # show what would be done
"""

import json
import random
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
USER_PHOTOS_DIR = DATA_DIR / "user_photos"
CROPS_DIR = DATA_DIR / "crops"
COCO_ANN = DATA_DIR / "NM_NGD_coco_dataset" / "annotations.json"

TARGET_SIZE = 260  # match classifier input
SEED = 42


def augment_photo(img, idx):
    """Generate augmented variants of a user photo."""
    variants = []

    # 1. Original resized
    variants.append(("orig", img.copy()))

    # 2. Horizontal flip
    variants.append(("flip", img.transpose(Image.FLIP_LEFT_RIGHT)))

    # 3. Random crops at different scales
    w, h = img.size
    for crop_idx, scale in enumerate([0.8, 0.85, 0.9]):
        cw, ch = int(w * scale), int(h * scale)
        # Center crop + small random offset
        random.seed(SEED + idx * 100 + crop_idx)
        max_dx = w - cw
        max_dy = h - ch
        dx = random.randint(0, max(0, max_dx))
        dy = random.randint(0, max(0, max_dy))
        cropped = img.crop((dx, dy, dx + cw, dy + ch))
        variants.append((f"crop{crop_idx}", cropped))

    # 4. Brightness/contrast variations
    for enhance_idx, (factor_b, factor_c) in enumerate([(1.2, 1.0), (0.8, 1.2), (1.0, 0.8)]):
        enhanced = ImageEnhance.Brightness(img).enhance(factor_b)
        enhanced = ImageEnhance.Contrast(enhanced).enhance(factor_c)
        variants.append((f"enh{enhance_idx}", enhanced))

    return variants


def process_photos(category_filter=None, dry_run=False):
    """Process user photos and add to crops directory."""
    if not USER_PHOTOS_DIR.exists():
        USER_PHOTOS_DIR.mkdir(parents=True)
        print(f"Created {USER_PHOTOS_DIR}/")
        print("Place photos in subdirectories named by category_id:")
        print(f"  {USER_PHOTOS_DIR}/213/photo1.jpg")
        print(f"  {USER_PHOTOS_DIR}/72/photo1.jpg")
        return

    # Load category names
    with open(COCO_ANN) as f:
        coco = json.load(f)
    cat_names = {cat["id"]: cat["name"] for cat in coco["categories"]}

    stats = defaultdict(int)

    for cat_dir in sorted(USER_PHOTOS_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        try:
            cat_id = int(cat_dir.name)
        except ValueError:
            print(f"Skipping {cat_dir.name} (not a valid category ID)")
            continue

        if category_filter is not None and cat_id != category_filter:
            continue

        if cat_id not in cat_names:
            print(f"Warning: category {cat_id} not in annotations!")
            continue

        photos = [p for p in cat_dir.iterdir()
                  if p.suffix.lower() in (".jpg", ".jpeg", ".png")]

        if not photos:
            continue

        out_dir = CROPS_DIR / str(cat_id)
        if not dry_run:
            out_dir.mkdir(parents=True, exist_ok=True)

        print(f"\nCategory {cat_id}: {cat_names[cat_id]}")
        print(f"  Found {len(photos)} user photos")

        for photo_idx, photo_path in enumerate(photos):
            img = Image.open(photo_path).convert("RGB")
            variants = augment_photo(img, photo_idx)

            for var_name, var_img in variants:
                # Resize to classifier input size
                var_img = var_img.resize((TARGET_SIZE, TARGET_SIZE), Image.BILINEAR)
                out_name = f"user_{photo_path.stem}_{var_name}.jpg"
                out_path = out_dir / out_name

                if dry_run:
                    print(f"  Would create: {out_path.name}")
                else:
                    var_img.save(out_path, quality=90)

                stats[cat_id] += 1

        print(f"  Generated {stats[cat_id]} augmented crops" +
              (" (dry run)" if dry_run else ""))

    if not stats:
        print(f"\nNo photos found in {USER_PHOTOS_DIR}/")
        print("Place photos in subdirectories named by category_id.")
        return

    total = sum(stats.values())
    print(f"\n{'='*50}")
    print(f"Total: {total} augmented crops across {len(stats)} categories")
    if not dry_run:
        print(f"\nNext steps:")
        print(f"  1. Re-run embeddings:  python3 precompute_embeddings.py")
        print(f"  2. Validate:           python3 validate.py")
        print(f"  3. For full retrain, upload crops to GCP VM and run train_classifier.py")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    process_photos(category_filter=args.category, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
