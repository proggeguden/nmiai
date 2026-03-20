"""Two-stage inference: YOLO detect → EfficientNet classify.

Stage 1: Single-class YOLOv8l detects all products (high recall)
Stage 2: EfficientNet-B2 classifies each crop into 356 categories
Final score = detection_confidence × classification_confidence
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

# Detector settings
DET_IMGSZ = 1280
DET_CONF = 0.10  # low threshold for high recall
DET_IOU = 0.5
DET_MAX_DET = 500

# Classifier settings
CLS_IMGSZ = 260  # EfficientNet-B2 native
CLS_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
CLS_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
PAD_RATIO = 0.05  # 5% padding around detection box


def create_session(path):
    """Create ONNX inference session with GPU if available."""
    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ort.InferenceSession(str(path), providers=providers)


def preprocess_detector(img, imgsz):
    """Preprocess image for YOLO ONNX model (letterbox + normalize)."""
    w, h = img.size
    scale = min(imgsz / w, imgsz / h)
    nw, nh = int(w * scale), int(h * scale)
    img_resized = img.resize((nw, nh), Image.BILINEAR)

    # Letterbox padding
    pad_w = (imgsz - nw) // 2
    pad_h = (imgsz - nh) // 2
    canvas = Image.new("RGB", (imgsz, imgsz), (114, 114, 114))
    canvas.paste(img_resized, (pad_w, pad_h))

    arr = np.array(canvas, dtype=np.float32) / 255.0
    arr = arr.transpose(2, 0, 1)[np.newaxis]  # BCHW
    return arr, scale, pad_w, pad_h


def postprocess_detector(output, scale, pad_w, pad_h, img_w, img_h, conf_thresh, iou_thresh, max_det):
    """Parse YOLO ONNX output to boxes. Output shape: (1, 5, num_anchors) for nc=1."""
    pred = output[0]  # (1, 5, N) — [x_center, y_center, w, h, conf]
    if pred.ndim == 3:
        pred = pred[0]  # (5, N)
    if pred.shape[0] < pred.shape[1]:
        pred = pred.T  # (N, 5)

    # Filter by confidence
    scores = pred[:, 4]
    mask = scores > conf_thresh
    pred = pred[mask]
    scores = scores[mask]

    if len(pred) == 0:
        return np.array([]), np.array([])

    # Convert center to corner format
    cx, cy, w, h = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
    x1 = cx - w / 2
    y1 = cy - h / 2
    x2 = cx + w / 2
    y2 = cy + h / 2

    # Undo letterbox transform
    x1 = (x1 - pad_w) / scale
    y1 = (y1 - pad_h) / scale
    x2 = (x2 - pad_w) / scale
    y2 = (y2 - pad_h) / scale

    # Clip to image bounds
    x1 = np.clip(x1, 0, img_w)
    y1 = np.clip(y1, 0, img_h)
    x2 = np.clip(x2, 0, img_w)
    y2 = np.clip(y2, 0, img_h)

    boxes = np.stack([x1, y1, x2, y2], axis=1)

    # NMS
    keep = nms(boxes, scores, iou_thresh)
    if len(keep) > max_det:
        keep = keep[:max_det]

    return boxes[keep], scores[keep]


def nms(boxes, scores, iou_thresh):
    """Simple NMS implementation."""
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
    """Crop detections from image and preprocess for classifier."""
    w_img, h_img = img.size
    crops = []

    for box in boxes:
        x1, y1, x2, y2 = box
        bw, bh = x2 - x1, y2 - y1

        # Add padding
        px, py = bw * PAD_RATIO, bh * PAD_RATIO
        cx1 = max(0, int(x1 - px))
        cy1 = max(0, int(y1 - py))
        cx2 = min(w_img, int(x2 + px))
        cy2 = min(h_img, int(y2 + py))

        crop = img.crop((cx1, cy1, cx2, cy2))
        crop = crop.resize((imgsz, imgsz), Image.BILINEAR)

        arr = np.array(crop, dtype=np.float32) / 255.0
        arr = (arr - CLS_MEAN) / CLS_STD
        arr = arr.transpose(2, 0, 1)  # CHW
        crops.append(arr)

    return np.array(crops, dtype=np.float32) if crops else np.zeros((0, 3, imgsz, imgsz), dtype=np.float32)


def softmax(x, axis=-1):
    """Numerically stable softmax."""
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

        # Stage 2: Classify crops in batches
        crop_batch = preprocess_crops(img, boxes, CLS_IMGSZ)
        batch_size = 64
        all_probs = []

        for i in range(0, len(crop_batch), batch_size):
            batch = crop_batch[i:i + batch_size]
            cls_output = cls_session.run(None, {cls_input_name: batch})
            probs = softmax(cls_output[0], axis=1)
            all_probs.append(probs)

        all_probs = np.concatenate(all_probs, axis=0)

        # Merge: final_score = det_conf * cls_conf
        for j in range(len(boxes)):
            x1, y1, x2, y2 = boxes[j]
            cls_id = int(np.argmax(all_probs[j]))
            cls_conf = float(all_probs[j, cls_id])
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
