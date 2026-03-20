"""Precompute classifier embeddings for kNN lookup.

Uses the trained EfficientNet-B2 to extract penultimate features from all
training crops + reference images. Saves as embeddings.npy for inference.

Output format: embeddings.npy shape (N, D+1) where:
    column 0 = category_id (int)
    columns 1: = embedding vector (float32)

Also exports classifier to ONNX with dual output (logits + features).

Run after train_classifier.py finishes:
    python3 precompute_embeddings.py [--letterbox] [--arcface]
"""

import json
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import timm
from PIL import Image
from torchvision import transforms

DATA_DIR = Path(__file__).parent / "data"
CROPS_DIR = DATA_DIR / "crops"
SAVE_DIR = Path(__file__).parent / "runs" / "classifier"
OUTPUT_DIR = Path(__file__).parent

IMG_SIZE = 260
BATCH_SIZE = 128
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]


class LetterboxResize:
    """Resize preserving aspect ratio, pad to square with mean color."""
    def __init__(self, size):
        self.size = size

    def __call__(self, img):
        w, h = img.size
        if w < 1 or h < 1:
            return Image.new("RGB", (self.size, self.size), (124, 116, 104))
        scale = min(self.size / w, self.size / h)
        nw, nh = int(w * scale), int(h * scale)
        resized = img.resize((nw, nh), Image.BILINEAR)
        canvas = Image.new("RGB", (self.size, self.size), (124, 116, 104))
        canvas.paste(resized, ((self.size - nw) // 2, (self.size - nh) // 2))
        return canvas


class DualOutputModel(nn.Module):
    """Wrapper that outputs both logits and penultimate features."""

    def __init__(self, model):
        super().__init__()
        self.model = model
        # EfficientNet-B2: features come from global_pool, logits from classifier
        # timm stores the classifier as model.classifier
        self.feature_dim = model.classifier.in_features

    def forward(self, x):
        features = self.model.forward_features(x)
        features = self.model.global_pool(features)
        if isinstance(features, tuple):
            features = features[0]
        # Flatten if needed
        features = features.view(features.size(0), -1)
        logits = self.model.classifier(features)
        return logits, features


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--letterbox", action="store_true",
                        help="Use letterbox transform (must match training)")
    parser.add_argument("--arcface", action="store_true",
                        help="Load ArcFace model (must match training)")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Load manifest
    with open(CROPS_DIR / "manifest.json") as f:
        manifest = json.load(f)

    num_classes = manifest["num_categories"]
    crops = manifest["crops"]
    print(f"Total crops: {len(crops)}, Classes: {num_classes}")

    if args.arcface:
        # Load ArcFace model — already outputs (logits, embeddings)
        from train_classifier import ArcFaceModel
        backbone = timm.create_model("efficientnet_b2", pretrained=False, num_classes=num_classes)
        model = ArcFaceModel(backbone, num_classes)
        state_dict = torch.load(SAVE_DIR / "best.pt", map_location=device, weights_only=True)
        model.load_state_dict(state_dict)
        model = model.to(device)
        model.eval()
        dual_model = model  # ArcFace already outputs (logits, features)
        print("Using ArcFace model (512-dim embeddings)")
    else:
        # Load standard model
        model = timm.create_model("efficientnet_b2", pretrained=False, num_classes=num_classes)
        state_dict = torch.load(SAVE_DIR / "best.pt", map_location=device, weights_only=True)
        model.load_state_dict(state_dict)
        model = model.to(device)
        model.eval()

        # Wrap for dual output
        dual_model = DualOutputModel(model).to(device)
        dual_model.eval()

    # Transform (must match training mode)
    if args.letterbox:
        print("Using LETTERBOX transform")
        transform = transforms.Compose([
            LetterboxResize(IMG_SIZE),
            transforms.ToTensor(),
            transforms.Normalize(mean=MEAN, std=STD),
        ])
    else:
        print("Using SQUASH transform")
        transform = transforms.Compose([
            transforms.Resize(int(IMG_SIZE * 1.1)),
            transforms.CenterCrop(IMG_SIZE),
            transforms.ToTensor(),
            transforms.Normalize(mean=MEAN, std=STD),
        ])

    # Extract embeddings for all crops
    print("Extracting embeddings...")
    all_embeddings = []
    all_labels = []

    batch_imgs = []
    batch_labels = []

    for i, crop in enumerate(crops):
        img_path = CROPS_DIR / crop["path"]
        if not img_path.exists():
            continue

        img = Image.open(img_path).convert("RGB")
        tensor = transform(img)
        batch_imgs.append(tensor)
        batch_labels.append(crop["category_id"])

        if len(batch_imgs) >= BATCH_SIZE or i == len(crops) - 1:
            batch = torch.stack(batch_imgs).to(device)
            with torch.no_grad():
                _, features = dual_model(batch)
            all_embeddings.append(features.cpu().numpy())
            all_labels.extend(batch_labels)
            batch_imgs = []
            batch_labels = []

            if (i + 1) % 5000 == 0:
                print(f"  Processed {i + 1}/{len(crops)}")

    embeddings = np.concatenate(all_embeddings, axis=0)
    labels = np.array(all_labels, dtype=np.float32)
    print(f"Embeddings shape: {embeddings.shape}")

    # Normalize embeddings for cosine similarity (L2 normalize)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / (norms + 1e-8)

    # Pack: column 0 = label, columns 1: = embedding
    packed = np.concatenate([labels.reshape(-1, 1), embeddings], axis=1).astype(np.float32)
    emb_path = OUTPUT_DIR / "embeddings.npy"
    np.save(emb_path, packed)
    emb_mb = emb_path.stat().st_size / (1024 * 1024)
    print(f"Saved embeddings to {emb_path} ({emb_mb:.1f} MB)")

    # Export dual-output ONNX
    print("\nExporting dual-output classifier ONNX...")
    dummy = torch.randn(1, 3, IMG_SIZE, IMG_SIZE).to(device)
    onnx_path = OUTPUT_DIR / "classifier.onnx"

    if args.arcface:
        # ArcFace model forward(x) without labels returns (logits, embeddings)
        torch.onnx.export(
            dual_model, (dummy,), str(onnx_path),
            input_names=["input"],
            output_names=["logits", "features"],
            dynamic_axes={
                "input": {0: "batch"},
                "logits": {0: "batch"},
                "features": {0: "batch"},
            },
            opset_version=17,
        )
    else:
        torch.onnx.export(
            dual_model, dummy, str(onnx_path),
            input_names=["input"],
            output_names=["logits", "features"],
            dynamic_axes={
                "input": {0: "batch"},
                "logits": {0: "batch"},
                "features": {0: "batch"},
            },
            opset_version=17,
        )
    onnx_mb = onnx_path.stat().st_size / (1024 * 1024)
    print(f"Exported to {onnx_path} ({onnx_mb:.1f} MB)")

    # Summary
    print(f"\n=== Ready for submission ===")
    print(f"  detector.onnx:   167 MB (already exported)")
    print(f"  classifier.onnx: {onnx_mb:.1f} MB")
    print(f"  embeddings.npy:  {emb_mb:.1f} MB")
    print(f"  Total:           {167 + onnx_mb + emb_mb:.1f} MB")


if __name__ == "__main__":
    main()
