"""Two-stage inference with kNN ensemble.

Stage 1: YOLOv8l single-class detection (high recall)
Stage 2: EfficientNet-B2 classification + kNN re-ranking
    - Classifier outputs logits + embeddings in one forward pass
    - kNN finds nearest training crops by cosine similarity
    - Final: 0.6 * classifier_softmax + 0.4 * knn_vote

Score = detection_confidence × classification_confidence
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

# Detector settings
DET_IMGSZ = 1280
DET_CONF = 0.10
DET_IOU = 0.5
DET_MAX_DET = 500

# Classifier settings
CLS_IMGSZ = 260
CLS_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
CLS_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
PAD_RATIO = 0.05

# kNN settings
KNN_K = 5
KNN_WEIGHT = 0.4  # weight for kNN in ensemble (classifier gets 1 - KNN_WEIGHT)


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
    probs = np.zeros((len(query_features), num_classes), dtype=np.float32)
    for i in range(len(query_features)):
        top_k_idx = np.argpartition(similarities[i], -k)[-k:]
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
    keep = nms(boxes, scores, iou_thresh)
    if len(keep) > max_det:
        keep = keep[:max_det]

    return boxes[keep], scores[keep]


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


def preprocess_crops(img, boxes, imgsz):
    w_img, h_img = img.size
    crops = []
    for box in boxes:
        x1, y1, x2, y2 = box
        bw, bh = x2 - x1, y2 - y1
        px, py = bw * PAD_RATIO, bh * PAD_RATIO
        cx1 = max(0, int(x1 - px))
        cy1 = max(0, int(y1 - py))
        cx2 = min(w_img, int(x2 + px))
        cy2 = min(h_img, int(y2 + py))

        crop = img.crop((cx1, cy1, cx2, cy2))
        crop = crop.resize((imgsz, imgsz), Image.BILINEAR)

        arr = np.array(crop, dtype=np.float32) / 255.0
        arr = (arr - CLS_MEAN) / CLS_STD
        arr = arr.transpose(2, 0, 1)
        crops.append(arr)

    return np.array(crops, dtype=np.float32) if crops else np.zeros((0, 3, imgsz, imgsz), dtype=np.float32)


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

    # Check if classifier has dual output (logits + features)
    cls_outputs = cls_session.get_outputs()
    has_features = len(cls_outputs) >= 2

    # Load kNN embeddings if available
    use_knn = EMBEDDINGS_PATH.exists() and has_features
    if use_knn:
        ref_labels, ref_embeddings = load_embeddings(EMBEDDINGS_PATH)
        num_classes = int(ref_labels.max()) + 1
    else:
        num_classes = 356

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
        crop_batch = preprocess_crops(img, boxes, CLS_IMGSZ)
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

        # kNN ensemble
        if use_knn and all_features:
            all_features = np.concatenate(all_features, axis=0)
            knn_probs = knn_predict(all_features, ref_embeddings, ref_labels, KNN_K, num_classes)
            # Ensemble: weighted average
            final_probs = (1 - KNN_WEIGHT) * cls_probs + KNN_WEIGHT * knn_probs
        else:
            final_probs = cls_probs

        # Build predictions
        for j in range(len(boxes)):
            x1, y1, x2, y2 = boxes[j]
            cls_id = int(np.argmax(final_probs[j]))
            cls_conf = float(final_probs[j, cls_id])
            det_conf = float(det_scores[j])
            final_score = det_conf * cls_conf

            predictions.append({
                "image_id": image_id,
                "category_id": cls_id,
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
