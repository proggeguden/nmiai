"""Visual diagnostics for detection + classification results.

Usage:
    # Generate all visualizations (requires val_predictions.json from validate.py):
    python3 analyze_results.py

    # Only confusion report:
    python3 analyze_results.py --confusion-only

    # Only annotated images:
    python3 analyze_results.py --viz-only
"""

import json
import random
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
COCO_ANN = DATA_DIR / "NM_NGD_coco_dataset" / "annotations.json"
IMAGES_DIR = DATA_DIR / "NM_NGD_coco_dataset" / "images"
REF_DIR = DATA_DIR / "NM_NGD_product_images"
VIZ_DIR = DATA_DIR / "viz"
GALLERY_DIR = DATA_DIR / "viz" / "galleries"
PREDICTIONS_FILE = ROOT / "val_predictions.json"
RESULTS_FILE = ROOT / "val_results.json"

SEED = 42
TRAIN_RATIO = 0.9
IOU_THRESHOLD = 0.5


def load_data():
    """Load annotations, predictions, and compute val split."""
    with open(COCO_ANN) as f:
        coco_data = json.load(f)

    with open(PREDICTIONS_FILE) as f:
        predictions = json.load(f)

    # Reproduce val split
    image_ids = sorted(img["id"] for img in coco_data["images"])
    random.seed(SEED)
    random.shuffle(image_ids)
    split_idx = int(len(image_ids) * TRAIN_RATIO)
    val_ids = set(image_ids[split_idx:])

    # Category names
    cat_names = {cat["id"]: cat["name"] for cat in coco_data["categories"]}

    # GT annotations for val images
    gt_anns = [ann for ann in coco_data["annotations"] if ann["image_id"] in val_ids]

    # Image info
    images = {img["id"]: img for img in coco_data["images"] if img["id"] in val_ids}

    return coco_data, predictions, val_ids, cat_names, gt_anns, images


def compute_iou(box_a, box_b):
    """Compute IoU between two [x, y, w, h] boxes."""
    ax1, ay1, aw, ah = box_a
    bx1, by1, bw, bh = box_b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area_a = aw * ah
    area_b = bw * bh
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0


def match_predictions_to_gt(predictions, gt_anns, images):
    """Match predictions to GT using greedy IoU matching.

    Returns:
        matches: list of (pred, gt_ann, iou) for true positives
        false_positives: list of pred dicts with no GT match
        false_negatives: list of GT anns with no pred match
        misclassified: list of (pred, gt_ann) where box matches but class differs
    """
    # Group by image
    preds_by_img = defaultdict(list)
    for p in predictions:
        preds_by_img[p["image_id"]].append(p)

    gt_by_img = defaultdict(list)
    for ann in gt_anns:
        gt_by_img[ann["image_id"]].append(ann)

    matches = []       # (pred, gt, iou) — correct class
    misclassified = [] # (pred, gt, iou) — wrong class
    false_positives = []
    false_negatives = []

    for img_id in set(list(preds_by_img.keys()) + list(gt_by_img.keys())):
        img_preds = sorted(preds_by_img[img_id], key=lambda p: -p["score"])
        img_gt = list(gt_by_img[img_id])
        gt_matched = [False] * len(img_gt)

        for pred in img_preds:
            best_iou = 0
            best_gt_idx = -1
            for g_idx, gt in enumerate(img_gt):
                if gt_matched[g_idx]:
                    continue
                iou = compute_iou(pred["bbox"], gt["bbox"])
                if iou > best_iou:
                    best_iou = iou
                    best_gt_idx = g_idx

            if best_iou >= IOU_THRESHOLD and best_gt_idx >= 0:
                gt_matched[best_gt_idx] = True
                gt = img_gt[best_gt_idx]
                if pred["category_id"] == gt["category_id"]:
                    matches.append((pred, gt, best_iou))
                else:
                    misclassified.append((pred, gt, best_iou))
            else:
                false_positives.append(pred)

        for g_idx, gt in enumerate(img_gt):
            if not gt_matched[g_idx]:
                false_negatives.append(gt)

    return matches, misclassified, false_positives, false_negatives


def draw_annotated_images(images, matches, misclassified, false_positives, false_negatives, cat_names):
    """Draw bounding boxes on val images with color coding."""
    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    # Try to load a font
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
    except (IOError, OSError):
        font = ImageFont.load_default()

    # Group everything by image
    by_img = defaultdict(lambda: {"match": [], "misc": [], "fp": [], "fn": []})

    for pred, gt, iou in matches:
        by_img[pred["image_id"]]["match"].append((pred, gt))
    for pred, gt, iou in misclassified:
        by_img[pred["image_id"]]["misc"].append((pred, gt))
    for pred in false_positives:
        by_img[pred["image_id"]]["fp"].append(pred)
    for gt in false_negatives:
        by_img[gt["image_id"]]["fn"].append(gt)

    id_to_fname = {img["id"]: img["file_name"] for img in images.values()}

    for img_id, data in by_img.items():
        fname = id_to_fname.get(img_id)
        if not fname:
            continue

        img_path = IMAGES_DIR / fname
        if not img_path.exists():
            continue

        img = Image.open(img_path).convert("RGB")
        draw = ImageDraw.Draw(img)

        # Green: correct detection + correct class
        for pred, gt in data["match"]:
            x, y, w, h = pred["bbox"]
            draw.rectangle([x, y, x + w, y + h], outline="green", width=2)
            label = f"{cat_names.get(pred['category_id'], '?')[:25]} ({pred['score']:.2f})"
            draw.text((x, max(0, y - 16)), label, fill="green", font=font)

        # Yellow: correct detection, wrong class
        for pred, gt in data["misc"]:
            x, y, w, h = pred["bbox"]
            draw.rectangle([x, y, x + w, y + h], outline="yellow", width=3)
            pred_name = cat_names.get(pred["category_id"], "?")[:20]
            gt_name = cat_names.get(gt["category_id"], "?")[:20]
            label = f"P:{pred_name} / GT:{gt_name}"
            draw.text((x, max(0, y - 16)), label, fill="yellow", font=font)

        # Red: false positive
        for pred in data["fp"]:
            x, y, w, h = pred["bbox"]
            draw.rectangle([x, y, x + w, y + h], outline="red", width=2)
            label = f"FP: {cat_names.get(pred['category_id'], '?')[:20]} ({pred['score']:.2f})"
            draw.text((x, max(0, y - 16)), label, fill="red", font=font)

        # Blue dashed: false negative (missed GT)
        for gt in data["fn"]:
            x, y, w, h = gt["bbox"]
            # Draw dashed rectangle (approximate with short segments)
            for i in range(0, int(2 * (w + h)), 8):
                if i < w:
                    draw.line([(x + i, y), (x + min(i + 4, w), y)], fill="cyan", width=2)
                    draw.line([(x + i, y + h), (x + min(i + 4, w), y + h)], fill="cyan", width=2)
                if i < h:
                    draw.line([(x, y + i), (x, y + min(i + 4, h))], fill="cyan", width=2)
                    draw.line([(x + w, y + i), (x + w, y + min(i + 4, h))], fill="cyan", width=2)
            gt_name = cat_names.get(gt["category_id"], "?")[:25]
            draw.text((x, max(0, y - 16)), f"MISS: {gt_name}", fill="cyan", font=font)

        # Add summary text
        n_match = len(data["match"])
        n_misc = len(data["misc"])
        n_fp = len(data["fp"])
        n_fn = len(data["fn"])
        summary = f"Correct: {n_match} | Misclassified: {n_misc} | FP: {n_fp} | Missed: {n_fn}"
        draw.text((10, 10), summary, fill="white", font=font)

        out_path = VIZ_DIR / f"val_{img_id:05d}.jpg"
        img.save(out_path, quality=85)

    print(f"Saved {len(by_img)} annotated images to {VIZ_DIR}/")


def print_confusion_report(misclassified, cat_names):
    """Print most common misclassification pairs."""
    print("\n" + "=" * 80)
    print("CONFUSION REPORT: Most common misclassifications")
    print("=" * 80)

    # Count (predicted_class, gt_class) pairs
    confusion = defaultdict(int)
    for pred, gt, iou in misclassified:
        key = (pred["category_id"], gt["category_id"])
        confusion[key] += 1

    if not confusion:
        print("No misclassifications found!")
        return

    # Sort by count
    sorted_conf = sorted(confusion.items(), key=lambda x: -x[1])

    print(f"\nTotal misclassified detections: {len(misclassified)}")
    print(f"\n{'#':<4} {'Count':<6} {'Predicted':<40} {'Actual (GT)':<40}")
    print("-" * 90)
    for (pred_id, gt_id), count in sorted_conf[:50]:
        pred_name = cat_names.get(pred_id, f"class_{pred_id}")[:38]
        gt_name = cat_names.get(gt_id, f"class_{gt_id}")[:38]
        print(f"{sorted_conf.index(((pred_id, gt_id), count)) + 1:<4} {count:<6} {pred_name:<40} {gt_name:<40}")

    # Group by product family
    families = {
        "WASA": [], "EGG": [], "TEA/TE": [], "KAFFE/COFFEE": [],
        "GRANOLA/MÜSLI": [], "NESCAFE": [], "GRISSINI": [], "MARGARIN/SMØR": [],
    }

    for (pred_id, gt_id), count in sorted_conf:
        pred_name = cat_names.get(pred_id, "").upper()
        gt_name = cat_names.get(gt_id, "").upper()
        for family_key in families:
            keywords = family_key.split("/")
            if any(kw in pred_name or kw in gt_name for kw in keywords):
                families[family_key].append((pred_id, gt_id, count))

    print("\n\nCONFUSION BY PRODUCT FAMILY:")
    for family, entries in families.items():
        if not entries:
            continue
        total = sum(c for _, _, c in entries)
        print(f"\n  {family} ({total} total confusions):")
        for pred_id, gt_id, count in entries[:10]:
            pred_name = cat_names.get(pred_id, "?")[:30]
            gt_name = cat_names.get(gt_id, "?")[:30]
            print(f"    {count:>3}x  {pred_name} ← {gt_name}")


def build_crop_galleries(misclassified, matches, cat_names, images, results_file):
    """Build crop galleries for weakest categories."""
    GALLERY_DIR.mkdir(parents=True, exist_ok=True)

    # Load per-class results to find worst categories
    if results_file.exists():
        with open(results_file) as f:
            results = json.load(f)
        per_class = results.get("per_class", {})
        # Sort by AP, filter to categories that have GT in val
        worst = [(int(cid), info) for cid, info in per_class.items()
                 if info["gt_count"] > 0]
        worst.sort(key=lambda x: x[1]["ap"])
        worst_ids = [cid for cid, _ in worst[:20]]
    else:
        print("No val_results.json found, skipping galleries.")
        return

    id_to_fname = {img["id"]: img["file_name"] for img in images.values()}

    # Load metadata for reference images
    meta_path = REF_DIR / "metadata.json"
    ref_by_cat = defaultdict(list)
    if meta_path.exists():
        with open(meta_path) as f:
            metadata = json.load(f)
        products = metadata.get("products", metadata) if isinstance(metadata, dict) else metadata
        cat_name_to_id = {cat_names[cid].lower(): cid for cid in cat_names}
        for product in products:
            pname = product.get("product_name", "").lower()
            cat_id = cat_name_to_id.get(pname)
            if cat_id is not None and product.get("has_images"):
                code = product["product_code"]
                ref_folder = REF_DIR / code
                if ref_folder.exists():
                    for img_file in sorted(ref_folder.iterdir()):
                        if img_file.suffix.lower() in (".jpg", ".jpeg", ".png"):
                            ref_by_cat[cat_id].append(img_file)

    # Collect correct and misclassified crops per category
    correct_by_cat = defaultdict(list)
    wrong_by_cat = defaultdict(list)  # GT category → (pred, gt)

    for pred, gt, iou in matches:
        correct_by_cat[gt["category_id"]].append((pred, gt))
    for pred, gt, iou in misclassified:
        wrong_by_cat[gt["category_id"]].append((pred, gt))

    thumb_size = 120

    for cat_id in worst_ids:
        name = cat_names.get(cat_id, f"class_{cat_id}")
        info = per_class.get(str(cat_id), {})
        ap = info.get("ap", -1)
        gt_count = info.get("gt_count", 0)

        # Collect images for each row
        ref_imgs = ref_by_cat.get(cat_id, [])[:6]
        correct = correct_by_cat.get(cat_id, [])[:6]
        wrong = wrong_by_cat.get(cat_id, [])[:6]

        n_cols = max(len(ref_imgs), len(correct), len(wrong), 1)
        n_rows = 3  # ref, correct, wrong
        margin = 5
        header_h = 25
        row_label_w = 90
        canvas_w = row_label_w + n_cols * (thumb_size + margin) + margin
        canvas_h = header_h + n_rows * (thumb_size + margin + 15) + margin

        canvas = Image.new("RGB", (canvas_w, canvas_h), (40, 40, 40))
        draw = ImageDraw.Draw(canvas)

        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
            font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 10)
        except (IOError, OSError):
            font = ImageFont.load_default()
            font_small = font

        # Header
        title = f"Cat {cat_id}: {name[:50]} | AP={ap:.3f} | GT={gt_count}"
        draw.text((margin, margin), title, fill="white", font=font)

        def paste_crops(row_idx, label, items, is_ref=False):
            y_start = header_h + row_idx * (thumb_size + margin + 15)
            draw.text((margin, y_start), label, fill="white", font=font_small)

            for col, item in enumerate(items):
                x = row_label_w + col * (thumb_size + margin)
                y = y_start + 15

                try:
                    if is_ref:
                        crop = Image.open(item).convert("RGB")
                    else:
                        pred, gt = item
                        fname = id_to_fname.get(gt["image_id"])
                        if not fname:
                            continue
                        img = Image.open(IMAGES_DIR / fname).convert("RGB")
                        bx, by, bw, bh = gt["bbox"]
                        crop = img.crop((int(bx), int(by), int(bx + bw), int(by + bh)))

                    crop = crop.resize((thumb_size, thumb_size), Image.BILINEAR)
                    canvas.paste(crop, (x, y))

                    if not is_ref and not (is_ref):
                        pred, gt = item
                        if pred["category_id"] != gt["category_id"]:
                            pred_name = cat_names.get(pred["category_id"], "?")[:15]
                            draw.text((x, y + thumb_size + 1), f"→{pred_name}", fill="red", font=font_small)
                except Exception:
                    draw.text((x, y + thumb_size // 2), "Error", fill="red", font=font_small)

        paste_crops(0, "Reference", ref_imgs, is_ref=True)
        paste_crops(1, "Correct", correct)
        paste_crops(2, "Wrong", wrong)

        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in name[:30])
        out_path = GALLERY_DIR / f"cat_{cat_id:03d}_{safe_name}.jpg"
        canvas.save(out_path, quality=90)

    print(f"Saved {len(worst_ids)} crop galleries to {GALLERY_DIR}/")


def print_summary(matches, misclassified, false_positives, false_negatives, cat_names):
    """Print overall summary stats."""
    total_gt = len(matches) + len(misclassified) + len(false_negatives)
    total_preds = len(matches) + len(misclassified) + len(false_positives)

    det_recall = (len(matches) + len(misclassified)) / total_gt if total_gt else 0
    det_precision = (len(matches) + len(misclassified)) / total_preds if total_preds else 0
    cls_accuracy = len(matches) / (len(matches) + len(misclassified)) if (len(matches) + len(misclassified)) else 0

    print("\n" + "=" * 60)
    print("OVERALL SUMMARY")
    print("=" * 60)
    print(f"Ground truth boxes:     {total_gt}")
    print(f"Predictions:            {total_preds}")
    print(f"True positives:         {len(matches)} (correct det + class)")
    print(f"Misclassified:          {len(misclassified)} (correct det, wrong class)")
    print(f"False positives:        {len(false_positives)} (no GT match)")
    print(f"False negatives:        {len(false_negatives)} (missed GT)")
    print(f"Detection recall:       {det_recall:.4f}")
    print(f"Detection precision:    {det_precision:.4f}")
    print(f"Classification accuracy: {cls_accuracy:.4f} (among matched detections)")
    print("=" * 60)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--confusion-only", action="store_true")
    parser.add_argument("--viz-only", action="store_true")
    args = parser.parse_args()

    if not PREDICTIONS_FILE.exists():
        print(f"Error: {PREDICTIONS_FILE} not found. Run validate.py first.")
        return

    print("Loading data...")
    coco_data, predictions, val_ids, cat_names, gt_anns, images = load_data()

    print("Matching predictions to ground truth...")
    matches, misclassified, false_positives, false_negatives = \
        match_predictions_to_gt(predictions, gt_anns, images)

    print_summary(matches, misclassified, false_positives, false_negatives, cat_names)

    if not args.viz_only:
        print_confusion_report(misclassified, cat_names)

    if not args.confusion_only:
        print("\nDrawing annotated images...")
        draw_annotated_images(images, matches, misclassified, false_positives, false_negatives, cat_names)

        print("\nBuilding crop galleries for weakest categories...")
        build_crop_galleries(misclassified, matches, cat_names, images, RESULTS_FILE)


if __name__ == "__main__":
    main()
