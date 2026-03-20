"""Generate a prioritized shopping list of products to photograph at the store.

Cross-references: annotation counts, reference image availability, confusion data.

Usage:
    python3 shopping_list.py
    python3 shopping_list.py --top 50  # show more products
"""

import json
import math
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
COCO_ANN = DATA_DIR / "NM_NGD_coco_dataset" / "annotations.json"
REF_DIR = DATA_DIR / "NM_NGD_product_images"
RESULTS_FILE = ROOT / "val_results.json"
PREDICTIONS_FILE = ROOT / "val_predictions.json"

SEED = 42
TRAIN_RATIO = 0.9


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=30, help="Show top N products")
    args = parser.parse_args()

    # Load annotations
    with open(COCO_ANN) as f:
        coco = json.load(f)

    cat_names = {cat["id"]: cat["name"] for cat in coco["categories"]}

    # Count annotations per category
    ann_counts = defaultdict(int)
    for ann in coco["annotations"]:
        ann_counts[ann["category_id"]] += 1

    # Compute val split to know which annotations are in train
    image_ids = sorted(img["id"] for img in coco["images"])
    random.seed(SEED)
    random.shuffle(image_ids)
    split_idx = int(len(image_ids) * TRAIN_RATIO)
    train_ids = set(image_ids[:split_idx])

    train_counts = defaultdict(int)
    for ann in coco["annotations"]:
        if ann["image_id"] in train_ids:
            train_counts[ann["category_id"]] += 1

    # Load metadata for reference images
    with open(REF_DIR / "metadata.json") as f:
        meta = json.load(f)

    products = meta.get("products", [])
    name_to_barcode = {}
    name_to_has_ref = {}
    for p in products:
        pname = p["product_name"].lower()
        name_to_barcode[pname] = p["product_code"]
        name_to_has_ref[pname] = p.get("has_images", False)

    # Load per-class results if available
    per_class_ap = {}
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            results = json.load(f)
        for cid, info in results.get("per_class", {}).items():
            per_class_ap[int(cid)] = info["ap"]

    # Load confusion data if available
    confusion_counts = defaultdict(int)  # category_id -> times it was confused
    if PREDICTIONS_FILE.exists() and COCO_ANN.exists():
        # Quick confusion analysis from predictions
        with open(PREDICTIONS_FILE) as f:
            preds = json.load(f)

        val_ids = set(image_ids[split_idx:])
        val_anns = [ann for ann in coco["annotations"] if ann["image_id"] in val_ids]

        # Group by image for matching
        preds_by_img = defaultdict(list)
        for p in preds:
            preds_by_img[p["image_id"]].append(p)
        gt_by_img = defaultdict(list)
        for ann in val_anns:
            gt_by_img[ann["image_id"]].append(ann)

        for img_id in gt_by_img:
            img_preds = sorted(preds_by_img[img_id], key=lambda p: -p["score"])
            img_gt = gt_by_img[img_id]
            gt_matched = [False] * len(img_gt)

            for pred in img_preds:
                best_iou = 0
                best_idx = -1
                for g_idx, gt in enumerate(img_gt):
                    if gt_matched[g_idx]:
                        continue
                    ax, ay, aw, ah = pred["bbox"]
                    bx, by, bw, bh = gt["bbox"]
                    ix1 = max(ax, bx)
                    iy1 = max(ay, by)
                    ix2 = min(ax + aw, bx + bw)
                    iy2 = min(ay + ah, by + bh)
                    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
                    union = aw * ah + bw * bh - inter
                    iou = inter / union if union > 0 else 0
                    if iou > best_iou:
                        best_iou = iou
                        best_idx = g_idx
                if best_iou >= 0.5 and best_idx >= 0:
                    gt_matched[best_idx] = True
                    gt = img_gt[best_idx]
                    if pred["category_id"] != gt["category_id"]:
                        confusion_counts[gt["category_id"]] += 1
                        confusion_counts[pred["category_id"]] += 1

    # Score each category
    scored = []
    for cat_id in cat_names:
        name = cat_names[cat_id]
        total_ann = ann_counts.get(cat_id, 0)
        train_ann = train_counts.get(cat_id, 0)
        has_ref = name_to_has_ref.get(name.lower(), False)
        barcode = name_to_barcode.get(name.lower(), "N/A")
        ap = per_class_ap.get(cat_id, None)
        confusion = confusion_counts.get(cat_id, 0)

        # Priority scoring:
        # - Fewer annotations = higher priority
        # - No reference images = 2x boost
        # - Low AP = boost (if measurable)
        # - Confused often = boost
        data_score = 1.0 / math.sqrt(total_ann + 1)
        ref_mult = 2.0 if not has_ref else 1.0
        confusion_bonus = 1.0 + confusion * 0.5
        ap_bonus = 1.0
        if ap is not None and ap >= 0:
            ap_bonus = 1.0 + (1.0 - ap)  # low AP → high bonus

        priority = data_score * ref_mult * confusion_bonus * ap_bonus

        scored.append({
            "cat_id": cat_id,
            "name": name,
            "barcode": barcode,
            "total_ann": total_ann,
            "train_ann": train_ann,
            "has_ref": has_ref,
            "ap": ap,
            "confusion": confusion,
            "priority": priority,
        })

    scored.sort(key=lambda x: -x["priority"])

    # Print shopping list
    print("=" * 100)
    print("SHOPPING LIST — Products to Photograph at the Store")
    print("=" * 100)
    print(f"\n{'#':<4} {'Priority':<9} {'CatID':<6} {'Ann':<5} {'AP':<7} {'Ref':<5} {'Conf':<5} {'Product Name':<45} {'Barcode'}")
    print("-" * 100)

    for i, item in enumerate(scored[:args.top], 1):
        ap_str = f"{item['ap']:.3f}" if item["ap"] is not None and item["ap"] >= 0 else "N/A"
        ref_str = "Yes" if item["has_ref"] else "NO"
        print(f"{i:<4} {item['priority']:<9.3f} {item['cat_id']:<6} {item['total_ann']:<5} "
              f"{ap_str:<7} {ref_str:<5} {item['confusion']:<5} {item['name']:<45} {item['barcode']}")

    # Summary stats
    n_zero_ap = sum(1 for s in scored if s["ap"] is not None and s["ap"] == 0)
    n_no_ref = sum(1 for s in scored if not s["has_ref"])
    n_few_ann = sum(1 for s in scored if s["total_ann"] <= 5)
    n_confused = sum(1 for s in scored if s["confusion"] > 0)

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Categories with AP = 0 in val:    {n_zero_ap}")
    print(f"Categories with NO ref images:    {n_no_ref}")
    print(f"Categories with ≤5 annotations:   {n_few_ann}")
    print(f"Categories confused at least once: {n_confused}")

    # Photo tips
    print(f"\n{'='*60}")
    print("PHOTOGRAPHY TIPS")
    print(f"{'='*60}")
    print("""
For each product on the list:
1. Take a FRONT photo (straight on, like a customer sees it on the shelf)
2. Take a SHELF CONTEXT photo (product on shelf with neighbors visible)
3. Take photos at SLIGHT ANGLES (±15°) to simulate real detection crops
4. Vary LIGHTING if possible (different aisle positions)
5. Include the BARCODE/label in at least one photo for verification

Most valuable: products with AP=0 or no reference images.
Egg products are the #1 confusion source — photograph EACH egg variant clearly,
especially showing the pack size (6 vs 10 vs 12) prominently.
""")

    # Save as text file for the store
    shopping_file = ROOT / "shopping_list.txt"
    with open(shopping_file, "w") as f:
        f.write("SHOPPING LIST — Products to Photograph\n")
        f.write("=" * 50 + "\n\n")
        for i, item in enumerate(scored[:args.top], 1):
            f.write(f"{i}. {item['name']}\n")
            f.write(f"   Barcode: {item['barcode']}\n")
            f.write(f"   Annotations: {item['total_ann']}, Has ref: {'Yes' if item['has_ref'] else 'NO'}\n")
            if item["confusion"] > 0:
                f.write(f"   ⚠ Confused {item['confusion']} times in val\n")
            f.write("\n")
    print(f"\nSaved printable list to {shopping_file}")


if __name__ == "__main__":
    main()
