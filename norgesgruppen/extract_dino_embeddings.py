"""Extract DINOv2 embeddings from dual-backbone ONNX using CPU inference.

Generates compact dino_embeddings.npy (float16, ~18MB) for kNN lookup.
Uses outputs[3] (dino_features, 384-dim) from the dual-backbone classifier.

Output: dino_embeddings.npy shape (N, 385) float16 where:
    column 0 = category_id
    columns 1: = L2-normalized DINOv2 embedding (384-dim)
"""

import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).parent
CROPS_DIR = ROOT / "data" / "crops"
CLASSIFIER_ONNX = ROOT / "classifier.onnx"
OUTPUT = ROOT / "dino_embeddings.npy"

IMG_SIZE = 260
BATCH_SIZE = 64
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def letterbox_resize(img, size):
    """Resize preserving aspect ratio, pad to square with mean color."""
    w, h = img.size
    if w < 1 or h < 1:
        return Image.new("RGB", (size, size), (124, 116, 104))
    scale = min(size / w, size / h)
    nw, nh = int(w * scale), int(h * scale)
    resized = img.resize((nw, nh), Image.BILINEAR)
    canvas = Image.new("RGB", (size, size), (124, 116, 104))
    canvas.paste(resized, ((size - nw) // 2, (size - nh) // 2))
    return canvas


def preprocess(img):
    """Letterbox resize + normalize to CHW float32."""
    img = letterbox_resize(img, IMG_SIZE)
    arr = np.array(img, dtype=np.float32) / 255.0
    arr = (arr - MEAN) / STD
    return arr.transpose(2, 0, 1)  # CHW


def main():
    import onnxruntime as ort

    # Load manifest
    with open(CROPS_DIR / "manifest.json") as f:
        manifest = json.load(f)
    crops = manifest["crops"]
    print(f"Total crops: {len(crops)}, Classes: {manifest['num_categories']}")

    # Load ONNX model (CPU)
    session = ort.InferenceSession(str(CLASSIFIER_ONNX), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    output_names = [o.name for o in session.get_outputs()]
    print(f"Outputs: {output_names}")
    assert "dino_features" in output_names, "classifier.onnx must be dual-backbone with dino_features output"

    all_embeddings = []
    all_labels = []
    batch_imgs = []
    batch_labels = []

    for i, crop in enumerate(crops):
        img_path = CROPS_DIR / crop["path"]
        if not img_path.exists():
            continue

        img = Image.open(img_path).convert("RGB")
        tensor = preprocess(img)
        batch_imgs.append(tensor)
        batch_labels.append(crop["category_id"])

        if len(batch_imgs) >= BATCH_SIZE or i == len(crops) - 1:
            batch = np.stack(batch_imgs).astype(np.float32)
            outputs = session.run(["dino_features"], {input_name: batch})
            all_embeddings.append(outputs[0])
            all_labels.extend(batch_labels)
            batch_imgs = []
            batch_labels = []

            if (i + 1) % 5000 == 0:
                print(f"  Processed {i + 1}/{len(crops)}")

    embeddings = np.concatenate(all_embeddings, axis=0)
    labels = np.array(all_labels, dtype=np.float32)
    print(f"Embeddings shape: {embeddings.shape}")

    # L2 normalize
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / (norms + 1e-8)

    # Pack: column 0 = label, columns 1: = embedding
    packed = np.concatenate([labels.reshape(-1, 1), embeddings], axis=1)

    # Save as float16 for compactness
    packed_f16 = packed.astype(np.float16)
    np.save(OUTPUT, packed_f16)
    size_mb = OUTPUT.stat().st_size / (1024 * 1024)
    print(f"Saved {OUTPUT} ({size_mb:.1f} MB, shape={packed_f16.shape}, dtype=float16)")


if __name__ == "__main__":
    main()
