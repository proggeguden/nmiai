"""Extract annotation crops + map reference images for classifier training.

Uses metadata.json to map barcode folder names to category_ids.

Outputs:
    data/crops/{category_id}/crop_{ann_id}.jpg   — cropped from shelf images
    data/crops/{category_id}/ref_{barcode}_{angle}.jpg — from reference images
    data/crops/manifest.json — metadata for all crops
"""

import json
from collections import Counter
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

    img_cache = {}
    manifest = []
    count = 0

    for ann in coco["annotations"]:
        img_info = images[ann["image_id"]]
        fname = img_info["file_name"]
        cat_id = ann["category_id"]
        ann_id = ann["id"]

        if fname not in img_cache:
            img_path = COCO_DIR / "images" / fname
            if not img_path.exists():
                continue
            img_cache[fname] = Image.open(img_path).convert("RGB")
            if len(img_cache) > 5:
                oldest = next(iter(img_cache))
                img_cache[oldest].close()
                del img_cache[oldest]

        img = img_cache[fname]
        w_img, h_img = img.size

        x, y, w, h = ann["bbox"]
        pad_x = w * PAD_RATIO
        pad_y = h * PAD_RATIO
        x1 = max(0, int(x - pad_x))
        y1 = max(0, int(y - pad_y))
        x2 = min(w_img, int(x + w + pad_x))
        y2 = min(h_img, int(y + h + pad_y))

        if x2 - x1 < 10 or y2 - y1 < 10:
            continue

        crop = img.crop((x1, y1, x2, y2))

        out_dir = CROPS_DIR / str(cat_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"crop_{ann_id}.jpg"
        crop.save(out_path, quality=90)

        manifest.append({
            "path": str(out_path.relative_to(CROPS_DIR)),
            "category_id": cat_id,
            "source": "annotation",
        })
        count += 1

    for img in img_cache.values():
        img.close()

    print(f"Extracted {count} annotation crops")
    return manifest, categories


def map_reference_images(categories):
    """Map reference product images to category_ids using metadata.json."""
    metadata_path = REF_DIR / "metadata.json"
    if not metadata_path.exists():
        print(f"metadata.json not found at {metadata_path}")
        return []

    with open(metadata_path) as f:
        meta = json.load(f)

    # Build product_name → category_id lookup (case-insensitive)
    name_to_id = {name.strip().lower(): cid for cid, name in categories.items()}

    # Build barcode → category_id mapping from metadata
    barcode_to_cat = {}
    for prod in meta["products"]:
        name = prod["product_name"].strip().lower()
        code = prod["product_code"]
        if name in name_to_id:
            barcode_to_cat[code] = name_to_id[name]

    print(f"Mapped {len(barcode_to_cat)} barcodes to category IDs")

    manifest = []
    matched_folders = 0

    for folder in sorted(REF_DIR.iterdir()):
        if not folder.is_dir():
            continue

        cat_id = barcode_to_cat.get(folder.name)
        if cat_id is None:
            continue

        matched_folders += 1
        for img_path in sorted(folder.iterdir()):
            if img_path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                continue

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
            })

    print(f"Reference images: {matched_folders} folders matched, {len(manifest)} images")
    return manifest


def main():
    print("=== Extracting annotation crops ===")
    ann_manifest, categories = extract_annotation_crops()

    print("\n=== Mapping reference images ===")
    ref_manifest = map_reference_images(categories)

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

    ann_counts = Counter(m["category_id"] for m in ann_manifest)
    ref_counts = Counter(m["category_id"] for m in ref_manifest)
    few_shot = sum(1 for c in categories if ann_counts.get(c, 0) < 5)
    boosted = sum(1 for c in categories if ann_counts.get(c, 0) < 5 and ref_counts.get(c, 0) > 0)
    print(f"\nCategories with <5 annotation crops: {few_shot}")
    print(f"Of those, boosted by reference images: {boosted}")
    print(f"Categories with reference images: {sum(1 for c in categories if ref_counts.get(c, 0) > 0)}")


if __name__ == "__main__":
    main()
