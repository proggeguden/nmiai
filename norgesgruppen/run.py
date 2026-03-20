"""Two-stage inference with optional WBF ensemble.

Pipeline A (two-stage): YOLOv8l single-class detect → EfficientNet-B2 classify (+ TTA)
Pipeline B (multi-class): YOLOv8m multi-class detect (356 classes)
WBF ensemble: fuse Pipeline A + Pipeline B predictions using Weighted Boxes Fusion

Score = detection_confidence × classification_confidence^SCORE_CLS_POWER
"""

import argparse
import json
import re
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

MODEL_DIR = Path(__file__).parent
DETECTOR_PATH = MODEL_DIR / "detector.onnx"
CLASSIFIER_PATH = MODEL_DIR / "classifier.onnx"
EMBEDDINGS_PATH = MODEL_DIR / "embeddings.npy"
MULTICLASS_PATH = MODEL_DIR / "multiclass_detector.onnx"

# Detector settings
DET_IMGSZ = 1280
DET_CONF = 0.10
DET_IOU = 0.5
DET_MAX_DET = 500
NUM_CLASSES = 356

# WBF ensemble settings
USE_WBF = True            # fuse two-stage + multi-class predictions
WBF_TWO_STAGE_WEIGHT = 0.6
WBF_MULTICLASS_WEIGHT = 0.4
WBF_IOU_THRESH = 0.5
WBF_SKIP_BOX_THRESH = 0.01

# Classifier settings
CLS_IMGSZ = 260
CLS_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
CLS_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
PAD_RATIO = 0.05

# Aspect ratio preservation
# Letterbox helps 6-pack eggs (+0.20 AP) but hurts 12-packs and overall score
# because the classifier was trained on squashed crops. REQUIRES RETRAINING.
# After retraining with letterbox crops: set USE_LETTERBOX_CROPS = True
USE_LETTERBOX_CROPS = False
USE_DUAL_CROPS = False
USE_ADAPTIVE_LETTERBOX = False   # letterbox TTA only for wide/tall crops
ADAPTIVE_AR_THRESHOLD = 1.5     # aspect ratio threshold for adaptive letterbox

# kNN settings
KNN_K = 5
KNN_WEIGHT = 0.4  # weight for kNN in ensemble (classifier gets 1 - KNN_WEIGHT)

# Soft-NMS settings (disabled — hurts on this dataset due to excess FPs)
USE_SOFT_NMS = False
SOFT_NMS_SIGMA = 0.5    # Gaussian decay parameter
SOFT_NMS_THRESH = 0.05  # prune boxes below this score after decay

# TTA settings
USE_TTA = True  # Test-time augmentation for classifier

# Score formula: final_score = det_conf * cls_conf^SCORE_CLS_POWER
# 1.0 = original multiplicative, 0.7 = best from sweep
SCORE_CLS_POWER = 0.7


def create_session(path):
    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ort.InferenceSession(str(path), providers=providers)


def load_embeddings(path):
    """Load precomputed embeddings. Format: column 0 = label, rest = embedding."""
    packed = np.load(str(path))
    labels = packed[:, 0].astype(np.int32)
    embeddings = packed[:, 1:]
    return labels, embeddings


def knn_predict(query_features, ref_embeddings, ref_labels, k, num_classes):
    """kNN classification using cosine similarity. Returns probability distribution."""
    # Normalize query features
    norms = np.linalg.norm(query_features, axis=1, keepdims=True)
    query_norm = query_features / (norms + 1e-8)

    # Cosine similarity: query_norm @ ref_embeddings.T (ref already normalized)
    similarities = query_norm @ ref_embeddings.T  # (batch, N_ref)

    # Get top-k for each query
    effective_k = min(k, len(ref_labels))
    probs = np.zeros((len(query_features), num_classes), dtype=np.float32)
    for i in range(len(query_features)):
        top_k_idx = np.argpartition(similarities[i], -effective_k)[-effective_k:]
        top_k_sims = similarities[i, top_k_idx]
        top_k_labels = ref_labels[top_k_idx]

        # Weight votes by similarity
        weights = np.maximum(top_k_sims, 0)  # clip negative similarities
        for label, weight in zip(top_k_labels, weights):
            probs[i, label] += weight

        # Normalize to probability distribution
        total = probs[i].sum()
        if total > 0:
            probs[i] /= total

    return probs


def preprocess_detector(img, imgsz):
    w, h = img.size
    scale = min(imgsz / w, imgsz / h)
    nw, nh = int(w * scale), int(h * scale)
    img_resized = img.resize((nw, nh), Image.BILINEAR)

    pad_w = (imgsz - nw) // 2
    pad_h = (imgsz - nh) // 2
    canvas = Image.new("RGB", (imgsz, imgsz), (114, 114, 114))
    canvas.paste(img_resized, (pad_w, pad_h))

    arr = np.array(canvas, dtype=np.float32) / 255.0
    arr = arr.transpose(2, 0, 1)[np.newaxis]
    return arr, scale, pad_w, pad_h


def postprocess_detector(output, scale, pad_w, pad_h, img_w, img_h, conf_thresh, iou_thresh, max_det):
    pred = output[0]
    if pred.ndim == 3:
        pred = pred[0]
    if pred.shape[0] < pred.shape[1]:
        pred = pred.T

    scores = pred[:, 4]
    mask = scores > conf_thresh
    pred = pred[mask]
    scores = scores[mask]

    if len(pred) == 0:
        return np.array([]), np.array([])

    cx, cy, w, h = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
    x1 = (cx - w / 2 - pad_w) / scale
    y1 = (cy - h / 2 - pad_h) / scale
    x2 = (cx + w / 2 - pad_w) / scale
    y2 = (cy + h / 2 - pad_h) / scale

    x1 = np.clip(x1, 0, img_w)
    y1 = np.clip(y1, 0, img_h)
    x2 = np.clip(x2, 0, img_w)
    y2 = np.clip(y2, 0, img_h)

    boxes = np.stack([x1, y1, x2, y2], axis=1)

    if USE_SOFT_NMS:
        boxes, scores = soft_nms(boxes, scores, sigma=SOFT_NMS_SIGMA, score_thresh=SOFT_NMS_THRESH)
    else:
        keep = nms(boxes, scores, iou_thresh)
        boxes = boxes[keep]
        scores = scores[keep]

    if len(boxes) > max_det:
        top_idx = np.argsort(scores)[::-1][:max_det]
        boxes = boxes[top_idx]
        scores = scores[top_idx]

    return boxes, scores


def nms(boxes, scores, iou_thresh):
    order = scores.argsort()[::-1]
    keep = []
    while len(order) > 0:
        i = order[0]
        keep.append(i)
        if len(order) == 1:
            break
        xx1 = np.maximum(boxes[i, 0], boxes[order[1:], 0])
        yy1 = np.maximum(boxes[i, 1], boxes[order[1:], 1])
        xx2 = np.minimum(boxes[i, 2], boxes[order[1:], 2])
        yy2 = np.minimum(boxes[i, 3], boxes[order[1:], 3])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        area_i = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        area_j = (boxes[order[1:], 2] - boxes[order[1:], 0]) * (boxes[order[1:], 3] - boxes[order[1:], 1])
        iou = inter / (area_i + area_j - inter + 1e-6)
        inds = np.where(iou <= iou_thresh)[0]
        order = order[inds + 1]
    return np.array(keep, dtype=int)


def soft_nms(boxes, scores, sigma=0.5, score_thresh=0.01):
    """Soft-NMS: decay overlapping box scores instead of removing them.

    For dense shelf images (97% have overlaps), this preserves valid detections
    that hard NMS would remove.
    """
    N = len(boxes)
    indices = np.arange(N)
    scores = scores.copy()

    # Sort by score descending
    order = scores.argsort()[::-1]
    boxes = boxes[order]
    scores = scores[order]

    keep_boxes = []
    keep_scores = []

    for i in range(N):
        if scores[i] < score_thresh:
            continue

        keep_boxes.append(boxes[i])
        keep_scores.append(scores[i])

        # Decay scores of remaining boxes based on overlap
        if i + 1 < N:
            xx1 = np.maximum(boxes[i, 0], boxes[i+1:, 0])
            yy1 = np.maximum(boxes[i, 1], boxes[i+1:, 1])
            xx2 = np.minimum(boxes[i, 2], boxes[i+1:, 2])
            yy2 = np.minimum(boxes[i, 3], boxes[i+1:, 3])
            inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
            area_i = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
            area_j = (boxes[i+1:, 2] - boxes[i+1:, 0]) * (boxes[i+1:, 3] - boxes[i+1:, 1])
            iou = inter / (area_i + area_j - inter + 1e-6)

            # Gaussian decay
            decay = np.exp(-iou ** 2 / sigma)
            scores[i+1:] *= decay

    if keep_boxes:
        return np.array(keep_boxes), np.array(keep_scores)
    return np.array([]).reshape(0, 4), np.array([])


def letterbox_crop(crop_pil, imgsz):
    """Resize crop preserving aspect ratio, pad to square with mean color.

    A 6-pack egg (wide) becomes a wide image with gray bars top/bottom.
    A 12-pack egg (even wider) gets a different pad pattern.
    This preserves the width/height ratio the classifier can learn from.
    """
    w, h = crop_pil.size
    if w < 1 or h < 1:
        return Image.new("RGB", (imgsz, imgsz), (124, 116, 104))
    scale = min(imgsz / w, imgsz / h)
    nw, nh = int(w * scale), int(h * scale)
    resized = crop_pil.resize((nw, nh), Image.BILINEAR)

    # Pad with approximate ImageNet mean color (in 0-255 range)
    pad_color = (124, 116, 104)  # ~= CLS_MEAN * 255
    canvas = Image.new("RGB", (imgsz, imgsz), pad_color)
    paste_x = (imgsz - nw) // 2
    paste_y = (imgsz - nh) // 2
    canvas.paste(resized, (paste_x, paste_y))
    return canvas


def extract_crop_pil(img, box):
    """Extract a padded crop from image given an xyxy box."""
    w_img, h_img = img.size
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    px, py = bw * PAD_RATIO, bh * PAD_RATIO
    cx1 = max(0, int(x1 - px))
    cy1 = max(0, int(y1 - py))
    cx2 = min(w_img, int(x2 + px))
    cy2 = min(h_img, int(y2 + py))
    return img.crop((cx1, cy1, cx2, cy2))


def crop_to_array(crop_pil, imgsz):
    """Convert a PIL crop to normalized numpy array for classifier."""
    if USE_LETTERBOX_CROPS:
        crop_pil = letterbox_crop(crop_pil, imgsz)
    else:
        crop_pil = crop_pil.resize((imgsz, imgsz), Image.BILINEAR)

    arr = np.array(crop_pil, dtype=np.float32) / 255.0
    arr = (arr - CLS_MEAN) / CLS_STD
    arr = arr.transpose(2, 0, 1)
    return arr


def preprocess_crops(img, boxes, imgsz):
    """Extract and preprocess crops from detected boxes."""
    crops = []
    for box in boxes:
        crop_pil = extract_crop_pil(img, box)
        crops.append(crop_to_array(crop_pil, imgsz))

    return np.array(crops, dtype=np.float32) if crops else np.zeros((0, 3, imgsz, imgsz), dtype=np.float32)


def preprocess_crops_tta(img, boxes, imgsz):
    """Extract crops with TTA augmentations.

    ADAPTIVE mode: 4 augments for square-ish crops (squash only),
                   6 augments for wide/tall crops (squash + letterbox).
    Returns variable-length arrays with per-box augment counts.
    """
    crops = []
    fill = (124, 116, 104)  # ~ImageNet mean
    n_augs_per_box = []  # track augment count per box

    for box in boxes:
        crop_pil = extract_crop_pil(img, box)
        w, h = crop_pil.size
        ar = max(w, h) / max(min(w, h), 1)

        # Standard squashed augments (always used)
        squashed = crop_pil.resize((imgsz, imgsz), Image.BILINEAR)
        variants = [
            squashed,                                       # original
            squashed.transpose(Image.FLIP_LEFT_RIGHT),      # flip
            squashed.rotate(5, fillcolor=fill),             # rot +5
            squashed.rotate(-5, fillcolor=fill),            # rot -5
        ]

        # Add letterbox augments for non-square crops
        if USE_ADAPTIVE_LETTERBOX and ar >= ADAPTIVE_AR_THRESHOLD:
            letterboxed = letterbox_crop(crop_pil, imgsz)
            variants.extend([
                letterboxed,                                    # letterbox original
                letterboxed.transpose(Image.FLIP_LEFT_RIGHT),  # letterbox flip
            ])

        n_augs_per_box.append(len(variants))

        for var in variants:
            arr = np.array(var, dtype=np.float32) / 255.0
            arr = (arr - CLS_MEAN) / CLS_STD
            arr = arr.transpose(2, 0, 1)
            crops.append(arr)

    if not crops:
        return np.zeros((0, 3, imgsz, imgsz), dtype=np.float32), n_augs_per_box

    return np.array(crops, dtype=np.float32), n_augs_per_box


def postprocess_multiclass(output, scale, pad_w, pad_h, img_w, img_h,
                           conf_thresh, iou_thresh, max_det, num_classes=356):
    """Postprocess multi-class YOLO output → boxes, scores, class_ids.

    Multi-class output shape: (1, 4+num_classes, num_anchors).
    """
    pred = output[0]
    if pred.ndim == 3:
        pred = pred[0]
    if pred.shape[0] < pred.shape[1]:
        pred = pred.T  # (num_anchors, 4+num_classes)

    # Split bbox and class scores
    bbox = pred[:, :4]  # cx, cy, w, h
    class_scores = pred[:, 4:]  # (num_anchors, num_classes)

    # Get best class per anchor
    class_ids = np.argmax(class_scores, axis=1)
    scores = class_scores[np.arange(len(class_ids)), class_ids]

    mask = scores > conf_thresh
    bbox = bbox[mask]
    scores = scores[mask]
    class_ids = class_ids[mask]

    if len(bbox) == 0:
        return np.array([]).reshape(0, 4), np.array([]), np.array([], dtype=int)

    cx, cy, w, h = bbox[:, 0], bbox[:, 1], bbox[:, 2], bbox[:, 3]
    x1 = (cx - w / 2 - pad_w) / scale
    y1 = (cy - h / 2 - pad_h) / scale
    x2 = (cx + w / 2 - pad_w) / scale
    y2 = (cy + h / 2 - pad_h) / scale

    x1 = np.clip(x1, 0, img_w)
    y1 = np.clip(y1, 0, img_h)
    x2 = np.clip(x2, 0, img_w)
    y2 = np.clip(y2, 0, img_h)

    boxes = np.stack([x1, y1, x2, y2], axis=1)

    # Per-class NMS
    keep_all = []
    for cls in np.unique(class_ids):
        cls_mask = class_ids == cls
        cls_boxes = boxes[cls_mask]
        cls_scores = scores[cls_mask]
        cls_indices = np.where(cls_mask)[0]
        keep = nms(cls_boxes, cls_scores, iou_thresh)
        keep_all.extend(cls_indices[keep].tolist())

    keep_all = np.array(keep_all, dtype=int)
    if len(keep_all) > max_det:
        top = np.argsort(scores[keep_all])[::-1][:max_det]
        keep_all = keep_all[top]

    return boxes[keep_all], scores[keep_all], class_ids[keep_all]


def wbf_fuse(boxes_list, scores_list, labels_list, weights, img_w, img_h,
             iou_thresh=0.5, skip_box_thresh=0.01):
    """Simple Weighted Boxes Fusion for 2 models.

    Normalizes boxes to [0,1], fuses overlapping boxes from different models,
    and returns the fused results.
    """
    # Normalize boxes to [0, 1]
    all_boxes = []
    all_scores = []
    all_labels = []

    for i, (boxes, scores, labels) in enumerate(zip(boxes_list, scores_list, labels_list)):
        if len(boxes) == 0:
            all_boxes.append(np.array([]).reshape(0, 4))
            all_scores.append(np.array([]))
            all_labels.append(np.array([], dtype=int))
            continue
        norm_boxes = boxes.copy()
        norm_boxes[:, [0, 2]] /= img_w
        norm_boxes[:, [1, 3]] /= img_h
        norm_boxes = np.clip(norm_boxes, 0, 1)
        all_boxes.append(norm_boxes)
        all_scores.append(scores * weights[i])
        all_labels.append(labels)

    # Simple fusion: take union of all boxes, merge overlapping ones
    if all(len(b) == 0 for b in all_boxes):
        return np.array([]).reshape(0, 4), np.array([]), np.array([], dtype=int)

    # Concatenate all predictions
    fused_boxes = np.concatenate([b for b in all_boxes if len(b) > 0], axis=0)
    fused_scores = np.concatenate([s for s in all_scores if len(s) > 0], axis=0)
    fused_labels = np.concatenate([l for l in all_labels if len(l) > 0], axis=0)

    # Filter low scores
    mask = fused_scores > skip_box_thresh
    fused_boxes = fused_boxes[mask]
    fused_scores = fused_scores[mask]
    fused_labels = fused_labels[mask]

    # Per-class NMS on fused set
    keep_all = []
    for cls in np.unique(fused_labels):
        cls_mask = fused_labels == cls
        cls_boxes = fused_boxes[cls_mask]
        cls_scores = fused_scores[cls_mask]
        cls_indices = np.where(cls_mask)[0]
        keep = nms(cls_boxes, cls_scores, iou_thresh)
        keep_all.extend(cls_indices[keep].tolist())

    keep_all = np.array(keep_all, dtype=int)

    # Denormalize boxes
    result_boxes = fused_boxes[keep_all].copy()
    result_boxes[:, [0, 2]] *= img_w
    result_boxes[:, [1, 3]] *= img_h

    return result_boxes, fused_scores[keep_all], fused_labels[keep_all]


def softmax(x, axis=-1):
    e = np.exp(x - np.max(x, axis=axis, keepdims=True))
    return e / e.sum(axis=axis, keepdims=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    # Load models
    det_session = create_session(DETECTOR_PATH)
    cls_session = create_session(CLASSIFIER_PATH)
    det_input_name = det_session.get_inputs()[0].name
    cls_input_name = cls_session.get_inputs()[0].name

    # Multi-class detector (optional)
    use_wbf = USE_WBF and MULTICLASS_PATH.exists()
    if use_wbf:
        mc_session = create_session(MULTICLASS_PATH)
        mc_input_name = mc_session.get_inputs()[0].name

    # Check if classifier has dual output (logits + features)
    cls_outputs = cls_session.get_outputs()
    has_features = len(cls_outputs) >= 2

    # Load kNN embeddings if available
    use_knn = EMBEDDINGS_PATH.exists() and has_features
    if use_knn:
        ref_labels, ref_embeddings = load_embeddings(EMBEDDINGS_PATH)
        num_classes = int(ref_labels.max()) + 1
    else:
        num_classes = NUM_CLASSES

    images_dir = Path(args.input)
    image_files = sorted(images_dir.glob("*.jpg"))
    if not image_files:
        image_files = sorted(images_dir.glob("*.png"))

    predictions = []

    for img_path in image_files:
        match = re.search(r"(\d+)", img_path.stem)
        image_id = int(match.group(1)) if match else 0

        img = Image.open(img_path).convert("RGB")
        w_img, h_img = img.size

        # Stage 1: Detect
        det_input, scale, pad_w, pad_h = preprocess_detector(img, DET_IMGSZ)
        det_output = det_session.run(None, {det_input_name: det_input})
        boxes, det_scores = postprocess_detector(
            det_output, scale, pad_w, pad_h, w_img, h_img,
            DET_CONF, DET_IOU, DET_MAX_DET
        )

        if len(boxes) == 0:
            continue

        # Stage 2: Classify + embed crops in batches
        if USE_TTA:
            crop_batch, n_augs = preprocess_crops_tta(img, boxes, CLS_IMGSZ)
        else:
            crop_batch = preprocess_crops(img, boxes, CLS_IMGSZ)
            n_augs = [1] * len(boxes)

        batch_size = 64
        all_logits = []
        all_features = []

        for i in range(0, len(crop_batch), batch_size):
            batch = crop_batch[i:i + batch_size]
            outputs = cls_session.run(None, {cls_input_name: batch})
            all_logits.append(outputs[0])
            if has_features:
                all_features.append(outputs[1])

        all_logits = np.concatenate(all_logits, axis=0)
        cls_probs = softmax(all_logits, axis=1)

        if has_features and all_features:
            all_features_cat = np.concatenate(all_features, axis=0)
        else:
            all_features_cat = None

        # Average TTA augmentations (variable augment count per box)
        n_boxes = len(boxes)
        avg_probs = np.zeros((n_boxes, cls_probs.shape[1]), dtype=np.float32)
        avg_features = np.zeros((n_boxes, all_features_cat.shape[1]), dtype=np.float32) if all_features_cat is not None else None
        offset = 0
        for j in range(n_boxes):
            n = n_augs[j]
            avg_probs[j] = cls_probs[offset:offset + n].mean(axis=0)
            if avg_features is not None:
                avg_features[j] = all_features_cat[offset:offset + n].mean(axis=0)
            offset += n
        cls_probs = avg_probs

        # kNN ensemble
        if use_knn and avg_features is not None:
            knn_probs = knn_predict(avg_features, ref_embeddings, ref_labels, KNN_K, num_classes)
            final_probs = (1 - KNN_WEIGHT) * cls_probs + KNN_WEIGHT * knn_probs
        else:
            final_probs = cls_probs

        # Build two-stage predictions (boxes are xyxy)
        ts_boxes_xyxy = boxes
        ts_scores = []
        ts_labels = []
        for j in range(len(boxes)):
            cls_id = int(np.argmax(final_probs[j]))
            cls_conf = float(final_probs[j, cls_id])
            det_conf = float(det_scores[j])
            final_score = det_conf * (cls_conf ** SCORE_CLS_POWER)
            ts_scores.append(final_score)
            ts_labels.append(cls_id)
        ts_scores = np.array(ts_scores)
        ts_labels = np.array(ts_labels, dtype=int)

        # WBF: fuse with multi-class detector
        if use_wbf:
            mc_output = mc_session.run(None, {mc_input_name: det_input})
            mc_boxes, mc_scores, mc_labels = postprocess_multiclass(
                mc_output, scale, pad_w, pad_h, w_img, h_img,
                DET_CONF, DET_IOU, DET_MAX_DET, NUM_CLASSES
            )

            fused_boxes, fused_scores, fused_labels = wbf_fuse(
                [ts_boxes_xyxy, mc_boxes],
                [ts_scores, mc_scores],
                [ts_labels, mc_labels],
                weights=[WBF_TWO_STAGE_WEIGHT, WBF_MULTICLASS_WEIGHT],
                img_w=w_img, img_h=h_img,
                iou_thresh=WBF_IOU_THRESH,
                skip_box_thresh=WBF_SKIP_BOX_THRESH,
            )
        else:
            fused_boxes = ts_boxes_xyxy
            fused_scores = ts_scores
            fused_labels = ts_labels

        # Build output predictions
        for j in range(len(fused_boxes)):
            x1, y1, x2, y2 = fused_boxes[j]
            final_score = float(fused_scores[j])

            predictions.append({
                "image_id": image_id,
                "category_id": int(fused_labels[j]),
                "bbox": [
                    round(float(x1), 2),
                    round(float(y1), 2),
                    round(float(x2 - x1), 2),
                    round(float(y2 - y1), 2),
                ],
                "score": round(final_score, 4),
            })

    output_path = Path(args.output)
    with open(output_path, "w") as f:
        json.dump(predictions, f)


if __name__ == "__main__":
    main()
