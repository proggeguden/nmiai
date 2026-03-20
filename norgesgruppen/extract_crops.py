"""Extract annotation crops + map reference images for classifier training.

Outputs:
    data/crops/{category_id}/crop_{ann_id}.jpg   — cropped from shelf images
    data/crops/{category_id}/ref_{folder}_{angle}.jpg — from reference images
    data/crops/manifest.json — metadata for all crops
"""

import json
from pathlib import Path
from PIL import Image

DATA_DIR = Path(__file__).parent / "data"
COCO_DIR = DATA_DIR / "NM_NGD_coco_dataset"
REF_DIR = DATA_DIR / "NM_NGD_product_images"
CROPS_DIR = DATA_DIR / "crops"
PAD_RATIO = 0.05  # 5% padding around bbox


def extract_annotation_crops():
    """Crop bounding boxes from training images."""
    with open(COCO_DIR / "annotations.json") as f:
        coco = json.load(f)

    images = {img["id"]: img for img in coco["images"]}
    categories = {cat["id"]: cat["name"] for cat in coco["categories"]}

    # Cache loaded images to avoid re-reading
    img_cache = {}
    manifest = []
    count = 0

    for ann in coco["annotations"]:
        img_info = images[ann["image_id"]]
        fname = img_info["file_name"]
        cat_id = ann["category_id"]
        ann_id = ann["id"]

        # Load image (cached)
        if fname not in img_cache:
            img_path = COCO_DIR / "images" / fname
            if not img_path.exists():
                continue
            img_cache[fname] = Image.open(img_path).convert("RGB")
            # Keep cache small — only keep last 5 images
            if len(img_cache) > 5:
                oldest = next(iter(img_cache))
                img_cache[oldest].close()
                del img_cache[oldest]

        img = img_cache[fname]
        w_img, h_img = img.size

        # COCO bbox: [x, y, w, h] absolute pixels
        x, y, w, h = ann["bbox"]

        # Add padding
        pad_x = w * PAD_RATIO
        pad_y = h * PAD_RATIO
        x1 = max(0, int(x - pad_x))
        y1 = max(0, int(y - pad_y))
        x2 = min(w_img, int(x + w + pad_x))
        y2 = min(h_img, int(y + h + pad_y))

        if x2 - x1 < 10 or y2 - y1 < 10:
            continue

        crop = img.crop((x1, y1, x2, y2))

        # Save crop
        out_dir = CROPS_DIR / str(cat_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"crop_{ann_id}.jpg"
        crop.save(out_path, quality=90)

        manifest.append({
            "path": str(out_path.relative_to(CROPS_DIR)),
            "category_id": cat_id,
            "source": "annotation",
            "image": fname,
            "ann_id": ann_id,
        })
        count += 1

    # Close remaining cached images
    for img in img_cache.values():
        img.close()

    print(f"Extracted {count} annotation crops")
    return manifest, categories


def map_reference_images(categories):
    """Map reference product images to category_ids."""
    if not REF_DIR.exists():
        print(f"Reference images not found at {REF_DIR}")
        return []

    # Build name→id lookup (lowercase, stripped)
    name_to_id = {}
    for cat_id, name in categories.items():
        name_to_id[name.strip().lower()] = cat_id

    manifest = []
    matched = 0
    unmatched = 0

    for folder in sorted(REF_DIR.iterdir()):
        if not folder.is_dir():
            continue

        folder_name = folder.name.strip()

        # Try exact match first, then case-insensitive
        cat_id = name_to_id.get(folder_name.lower())

        if cat_id is None:
            unmatched += 1
            continue

        matched += 1
        for img_path in sorted(folder.glob("*.jpg")) + sorted(folder.glob("*.png")) + sorted(folder.glob("*.JPG")):
            # Copy/link reference image to crops directory
            out_dir = CROPS_DIR / str(cat_id)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"ref_{folder.name}_{img_path.name}"

            if not out_path.exists():
                img = Image.open(img_path).convert("RGB")
                img.save(out_path, quality=90)
                img.close()

            manifest.append({
                "path": str(out_path.relative_to(CROPS_DIR)),
                "category_id": cat_id,
                "source": "reference",
                "folder": folder.name,
            })

    print(f"Reference images: {matched} folders matched, {unmatched} unmatched")
    print(f"Total reference crops: {len(manifest)}")
    return manifest


def main():
    print("=== Extracting annotation crops ===")
    ann_manifest, categories = extract_annotation_crops()

    print("\n=== Mapping reference images ===")
    ref_manifest = map_reference_images(categories)

    # Combine and save manifest
    full_manifest = ann_manifest + ref_manifest
    manifest_path = CROPS_DIR / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump({
            "crops": full_manifest,
            "num_categories": len(categories),
            "categories": {str(k): v for k, v in categories.items()},
            "stats": {
                "annotation_crops": len(ann_manifest),
                "reference_crops": len(ref_manifest),
                "total": len(full_manifest),
            }
        }, f, indent=2)

    print(f"\nManifest written to {manifest_path}")

    # Print per-class stats
    from collections import Counter
    ann_counts = Counter(m["category_id"] for m in ann_manifest)
    ref_counts = Counter(m["category_id"] for m in ref_manifest)

    few_shot = sum(1 for c in categories if ann_counts.get(c, 0) < 5)
    boosted = sum(1 for c in categories if ann_counts.get(c, 0) < 5 and ref_counts.get(c, 0) > 0)
    print(f"\nCategories with <5 annotation crops: {few_shot}")
    print(f"Of those, boosted by reference images: {boosted}")


if __name__ == "__main__":
    main()
