"""Merge EfficientNet-B2 + DINOv2 into a single dual-backbone ONNX model.

Both models share the same input (260×260 crop) and output separate logits.
At inference, run.py ensembles: 0.5 × EfficientNet + 0.5 × DINOv2.

This keeps us within the 3-file weight limit (detector.onnx + classifier.onnx + multiclass_detector.onnx).

Usage:
    python3 build_dual_classifier.py
    # Creates classifier.onnx with 4 outputs: effnet_logits, effnet_features, dino_logits, dino_features

Requires both models trained:
    - runs/classifier/best.pt (EfficientNet-B2)
    - runs/dino_classifier/best.pt (DINOv2-ViT-S)
"""

import json
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import timm

SAVE_DIR = Path(__file__).parent
EFFNET_DIR = SAVE_DIR / "runs" / "classifier"
DINO_DIR = SAVE_DIR / "runs" / "dino_classifier"
CROPS_DIR = SAVE_DIR / "data" / "crops"

IMG_SIZE = 260
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]


DINO_IMG_SIZE = 252  # DINOv2 needs input divisible by 14 (patch size)


class DualBackboneClassifier(nn.Module):
    """Combined EfficientNet-B2 + DINOv2-ViT-S classifier.

    Single input (260×260) → four outputs:
      - effnet_logits: EfficientNet classification logits
      - effnet_features: EfficientNet penultimate features (for kNN)
      - dino_logits: DINOv2 classification logits
      - dino_features: DINOv2 features (for kNN)

    DINOv2 internally resizes 260→252 (must be divisible by patch size 14).
    """
    def __init__(self, effnet_model, dino_model):
        super().__init__()
        self.effnet = effnet_model
        self.dino_backbone = dino_model.backbone
        self.dino_head = dino_model.head

        # EfficientNet feature extraction
        self.effnet_feat_dim = effnet_model.classifier.in_features

    def forward(self, x):
        # EfficientNet path (260×260)
        eff_features = self.effnet.forward_features(x)
        eff_features = self.effnet.global_pool(eff_features)
        if isinstance(eff_features, tuple):
            eff_features = eff_features[0]
        eff_features = eff_features.view(eff_features.size(0), -1)
        eff_logits = self.effnet.classifier(eff_features)

        # DINOv2 path (resize 260→252 for patch size compatibility)
        x_dino = torch.nn.functional.interpolate(
            x, size=(DINO_IMG_SIZE, DINO_IMG_SIZE), mode="bilinear", align_corners=False
        )
        dino_features = self.dino_backbone(x_dino)
        dino_logits = self.dino_head(dino_features)

        return eff_logits, eff_features, dino_logits, dino_features


def load_dino_model(num_classes, device):
    """Load trained DINOv2 classifier."""
    # Import the model class
    from train_dino_classifier import DINOClassifier

    model = DINOClassifier(num_classes)
    state_dict = torch.load(DINO_DIR / "best.pt", map_location=device, weights_only=True)
    model.load_state_dict(state_dict)
    model.eval()
    return model


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="efficientnet_b2",
                        help="timm model name (default: efficientnet_b2)")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Get num_classes from manifest (or default to 356)
    manifest_path = CROPS_DIR / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
        num_classes = manifest["num_categories"]
    else:
        num_classes = 356
        manifest = None
    print(f"Classes: {num_classes}")

    # Load EfficientNet
    print(f"Loading {args.model}...")
    effnet = timm.create_model(args.model, pretrained=False, num_classes=num_classes)
    effnet_state = torch.load(EFFNET_DIR / "best.pt", map_location=device, weights_only=True)
    effnet.load_state_dict(effnet_state)
    effnet.eval()

    # Load DINOv2
    print("Loading DINOv2-ViT-S...")
    dino_model = load_dino_model(num_classes, device)

    # Build dual model
    print("Building dual-backbone model...")
    dual = DualBackboneClassifier(effnet, dino_model).to(device)
    dual.eval()

    # Test forward pass
    dummy = torch.randn(1, 3, IMG_SIZE, IMG_SIZE).to(device)
    with torch.no_grad():
        eff_logits, eff_features, dino_logits, dino_features = dual(dummy)
    print(f"EfficientNet: logits={eff_logits.shape}, features={eff_features.shape}")
    print(f"DINOv2: logits={dino_logits.shape}, features={dino_features.shape}")

    # Export to ONNX
    print("\nExporting dual-backbone ONNX...")
    onnx_path = SAVE_DIR / "classifier.onnx"
    torch.onnx.export(
        dual, dummy, str(onnx_path),
        input_names=["input"],
        output_names=["logits", "features", "dino_logits", "dino_features"],
        dynamic_axes={
            "input": {0: "batch"},
            "logits": {0: "batch"},
            "features": {0: "batch"},
            "dino_logits": {0: "batch"},
            "dino_features": {0: "batch"},
        },
        opset_version=17,
    )
    onnx_mb = onnx_path.stat().st_size / (1024 * 1024)
    print(f"Exported to {onnx_path} ({onnx_mb:.1f} MB)")

    # Precompute DINOv2 embeddings for kNN (only if crops data available)
    emb_mb = 0
    if manifest is not None and CROPS_DIR.exists():
        print("\nPrecomputing DINOv2 embeddings...")
        from torchvision import transforms
        from PIL import Image

        transform = transforms.Compose([
            transforms.Resize(int(IMG_SIZE * 1.1)),
            transforms.CenterCrop(IMG_SIZE),
            transforms.ToTensor(),
            transforms.Normalize(mean=MEAN, std=STD),
        ])

        all_embeddings = []
        all_labels = []
        batch_imgs = []
        batch_labels = []

        for i, crop in enumerate(manifest["crops"]):
            img_path = CROPS_DIR / crop["path"]
            if not img_path.exists():
                continue
            img = Image.open(img_path).convert("RGB")
            tensor = transform(img)
            batch_imgs.append(tensor)
            batch_labels.append(crop["category_id"])

            if len(batch_imgs) >= 128 or i == len(manifest["crops"]) - 1:
                batch = torch.stack(batch_imgs).to(device)
                with torch.no_grad():
                    _, _, _, dino_feats = dual(batch)
                all_embeddings.append(dino_feats.cpu().numpy())
                all_labels.extend(batch_labels)
                batch_imgs = []
                batch_labels = []

        embeddings = np.concatenate(all_embeddings, axis=0)
        labels = np.array(all_labels, dtype=np.float32)

        # L2 normalize
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / (norms + 1e-8)

        packed = np.concatenate([labels.reshape(-1, 1), embeddings], axis=1).astype(np.float32)
        emb_path = SAVE_DIR / "embeddings.npy"
        np.save(emb_path, packed)
        emb_mb = emb_path.stat().st_size / (1024 * 1024)
        print(f"Saved embeddings to {emb_path} ({emb_mb:.1f} MB)")
    else:
        print("\nSkipping embeddings (no crops data available)")

    # Summary
    total = onnx_mb + emb_mb + 167 + 100  # detector + multiclass
    print(f"\n=== Weight Budget ===")
    print(f"  detector.onnx:            167 MB")
    print(f"  classifier.onnx (dual):   {onnx_mb:.1f} MB")
    print(f"  multiclass_detector.onnx: 100 MB")
    print(f"  Total:                    {total:.1f} MB / 420 MB limit")

    if total > 420:
        print(f"  WARNING: Over budget by {total - 420:.1f} MB!")
        print(f"  Consider dropping embeddings.npy and using classifier-only mode")
    else:
        print(f"  Headroom:                 {420 - total:.1f} MB")


if __name__ == "__main__":
    main()
