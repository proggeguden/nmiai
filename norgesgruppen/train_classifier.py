"""Train EfficientNet-B2 classifier on annotation crops + reference images.

Setup:
    pip3 install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
    pip3 install timm==0.9.12 Pillow
    python3 extract_crops.py   # must run first
    python3 train_classifier.py [--letterbox] [--arcface] [--aggressive-aug]
"""

import json
import math
from collections import Counter
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler
from torchvision import transforms
from torchvision.transforms import functional as TF
from PIL import Image
import timm

DATA_DIR = Path(__file__).parent / "data"
CROPS_DIR = DATA_DIR / "crops"
SAVE_DIR = Path(__file__).parent / "runs" / "classifier"

IMG_SIZE = 260  # EfficientNet-B2 native resolution
BATCH_SIZE = 192
NUM_EPOCHS = 80
LR = 3e-3  # scale with batch size (3x batch → 3x LR)
LABEL_SMOOTHING = 0.1
NUM_WORKERS = 8
REF_OVERSAMPLE = 10  # oversample reference images for rare classes
USE_AMP = True  # mixed precision for speed

# ArcFace settings
ARCFACE_EMBEDDING_DIM = 512
ARCFACE_MARGIN = 0.5
ARCFACE_SCALE = 64.0


class LetterboxResize:
    """Resize preserving aspect ratio, pad to square with mean color.

    This preserves width/height information (critical for egg 6-pack vs 12-pack).
    Pad color = ImageNet mean * 255 ≈ (124, 116, 104).
    """
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


class LetterboxRandomResizedCrop:
    """Letterbox + random scale/translate augmentation.

    1. Letterbox to target_size (preserving AR)
    2. Random scale (zoom in/out within the letterboxed image)
    3. Random translate (shift within padded area)
    """
    def __init__(self, size, scale=(0.75, 1.0)):
        self.size = size
        self.scale = scale

    def __call__(self, img):
        import random
        w, h = img.size
        if w < 1 or h < 1:
            return Image.new("RGB", (self.size, self.size), (124, 116, 104))

        # Random scale factor
        s = random.uniform(self.scale[0], self.scale[1])
        target = int(self.size / s)

        # Letterbox to target size
        scale = min(target / w, target / h)
        nw, nh = int(w * scale), int(h * scale)
        resized = img.resize((nw, nh), Image.BILINEAR)

        # Place on canvas with random offset
        canvas = Image.new("RGB", (target, target), (124, 116, 104))
        max_x = max(0, target - nw)
        max_y = max(0, target - nh)
        px = random.randint(0, max_x) if max_x > 0 else 0
        py = random.randint(0, max_y) if max_y > 0 else 0
        canvas.paste(resized, (px, py))

        # Center crop back to self.size
        if target > self.size:
            left = (target - self.size) // 2
            top = (target - self.size) // 2
            canvas = canvas.crop((left, top, left + self.size, top + self.size))
        elif target < self.size:
            final = Image.new("RGB", (self.size, self.size), (124, 116, 104))
            offset = (self.size - target) // 2
            final.paste(canvas, (offset, offset))
            canvas = final

        return canvas


class ArcFaceHead(nn.Module):
    """ArcFace angular margin loss head.

    Adds angular margin penalty to make the classifier learn tighter clusters.
    Critical for confusable products (eggs, WASA variants, Nescafé).
    """
    def __init__(self, embedding_dim, num_classes, margin=0.5, scale=64.0):
        super().__init__()
        self.scale = scale
        self.margin = margin
        self.weight = nn.Parameter(torch.FloatTensor(num_classes, embedding_dim))
        nn.init.xavier_uniform_(self.weight)

    def forward(self, embeddings, labels=None):
        # Normalize embeddings and weights
        embeddings_norm = F.normalize(embeddings, p=2, dim=1)
        weight_norm = F.normalize(self.weight, p=2, dim=1)

        # Cosine similarity
        cosine = F.linear(embeddings_norm, weight_norm)

        if labels is None:
            # Inference: just return scaled cosine
            return cosine * self.scale

        # Training: add angular margin to target class
        theta = torch.acos(torch.clamp(cosine, -1.0 + 1e-7, 1.0 - 1e-7))
        one_hot = torch.zeros_like(cosine)
        one_hot.scatter_(1, labels.unsqueeze(1), 1.0)

        # Add margin to target angle
        target_logits = torch.cos(theta + self.margin)
        logits = cosine * (1 - one_hot) + target_logits * one_hot

        return logits * self.scale


class ArcFaceModel(nn.Module):
    """EfficientNet-B2 with ArcFace embedding head."""
    def __init__(self, backbone, num_classes, embedding_dim=512):
        super().__init__()
        self.backbone = backbone
        # Replace classifier with embedding projection
        in_features = backbone.classifier.in_features
        backbone.classifier = nn.Identity()
        self.embedding = nn.Linear(in_features, embedding_dim)
        self.bn = nn.BatchNorm1d(embedding_dim)
        self.arcface = ArcFaceHead(embedding_dim, num_classes,
                                    margin=ARCFACE_MARGIN, scale=ARCFACE_SCALE)

    def forward(self, x, labels=None):
        features = self.backbone(x)
        embeddings = self.bn(self.embedding(features))
        logits = self.arcface(embeddings, labels)
        return logits, embeddings


class CropDataset(Dataset):
    def __init__(self, entries, transform=None):
        self.entries = entries
        self.transform = transform

    def __len__(self):
        return len(self.entries)

    def __getitem__(self, idx):
        entry = self.entries[idx]
        img_path = CROPS_DIR / entry["path"]
        img = Image.open(img_path).convert("RGB")
        if self.transform:
            img = self.transform(img)
        return img, entry["category_id"]


def build_datasets(manifest_path, full_train=False):
    """Build train/val datasets with oversampling for rare classes."""
    with open(manifest_path) as f:
        manifest = json.load(f)

    crops = manifest["crops"]
    num_classes = manifest["num_categories"]

    # Split: use crops from val images for val, rest for train
    # We use annotation source info to split
    # For simplicity: 90% train, 10% val (random but stratified)
    import random
    random.seed(42)

    # Group by category
    by_cat = {}
    for c in crops:
        by_cat.setdefault(c["category_id"], []).append(c)

    train_entries = []
    val_entries = []

    for cat_id, entries in by_cat.items():
        ann_entries = [e for e in entries if e["source"] == "annotation"]
        ref_entries = [e for e in entries if e["source"] == "reference"]

        if full_train:
            train_ann = ann_entries  # ALL annotations to train
            val_ann = []
        else:
            # Split annotations 90/10
            random.shuffle(ann_entries)
            split = max(1, int(len(ann_entries) * 0.9))
            train_ann = ann_entries[:split]
            val_ann = ann_entries[split:] if len(ann_entries) > 1 else []

        # Oversample reference images for rare classes
        if len(train_ann) < 20 and ref_entries:
            oversample_factor = REF_OVERSAMPLE
        elif ref_entries:
            oversample_factor = 3
        else:
            oversample_factor = 0

        train_entries.extend(train_ann)
        train_entries.extend(ref_entries * oversample_factor)

        # Val only uses annotation crops (real data)
        val_entries.extend(val_ann)

    print(f"Train: {len(train_entries)} samples, Val: {len(val_entries)} samples")
    print(f"Classes: {num_classes}")
    return train_entries, val_entries, num_classes


def build_sampler(entries):
    """Weighted sampler to handle class imbalance: weight = 1/sqrt(count)."""
    counts = Counter(e["category_id"] for e in entries)
    weights = []
    for e in entries:
        w = 1.0 / math.sqrt(counts[e["category_id"]])
        weights.append(w)
    return WeightedRandomSampler(weights, len(weights), replacement=True)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--letterbox", action="store_true",
                        help="Use letterbox (aspect-ratio-preserving) crops instead of squashed")
    parser.add_argument("--arcface", action="store_true",
                        help="Use ArcFace angular margin loss instead of softmax CE")
    parser.add_argument("--aggressive-aug", action="store_true",
                        help="Use aggressive domain augmentation for robustness to store variation")
    parser.add_argument("--epochs", type=int, default=None,
                        help="Override number of training epochs (default: 80)")
    parser.add_argument("--model", type=str, default="efficientnet_b2",
                        help="timm model name (default: efficientnet_b2)")
    parser.add_argument("--batch-size", type=int, default=None,
                        help="Override batch size (default: 192)")
    parser.add_argument("--full-train", action="store_true",
                        help="Train on ALL data (no validation holdout) for final submission")
    args = parser.parse_args()

    global NUM_EPOCHS, BATCH_SIZE
    if args.epochs is not None:
        NUM_EPOCHS = args.epochs
    if args.batch_size is not None:
        BATCH_SIZE = args.batch_size

    manifest_path = CROPS_DIR / "manifest.json"
    if not manifest_path.exists():
        print("Error: Run extract_crops.py first!")
        return

    train_entries, val_entries, num_classes = build_datasets(manifest_path, full_train=args.full_train)

    # Augmentation params: default vs aggressive
    if args.aggressive_aug:
        print("Using AGGRESSIVE augmentation (for domain robustness)")
        brightness, contrast, saturation, hue = 0.5, 0.5, 0.4, 0.1
        rotation = 20
        extra_augs = [
            transforms.RandomGrayscale(p=0.05),
            transforms.GaussianBlur(kernel_size=3, sigma=(0.1, 2.0)),
            transforms.RandomPosterize(bits=6, p=0.1),
        ]
    else:
        brightness, contrast, saturation, hue = 0.3, 0.3, 0.3, 0.05
        rotation = 15
        extra_augs = []

    # Transforms
    if args.letterbox:
        print("Using LETTERBOX transforms (preserving aspect ratio)")
        train_transform = transforms.Compose([
            LetterboxRandomResizedCrop(IMG_SIZE, scale=(0.75, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(brightness=brightness, contrast=contrast,
                                   saturation=saturation, hue=hue),
            transforms.RandomRotation(rotation),
            *extra_augs,
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            transforms.RandomErasing(p=0.3),
        ])
        val_transform = transforms.Compose([
            LetterboxResize(IMG_SIZE),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])
    else:
        print("Using SQUASH transforms (original)")
        train_transform = transforms.Compose([
            transforms.RandomResizedCrop(IMG_SIZE, scale=(0.7, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(brightness=brightness, contrast=contrast,
                                   saturation=saturation, hue=hue),
            transforms.RandomRotation(rotation),
            *extra_augs,
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            transforms.RandomErasing(p=0.3),
        ])
        val_transform = transforms.Compose([
            transforms.Resize(int(IMG_SIZE * 1.1)),
            transforms.CenterCrop(IMG_SIZE),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

    train_ds = CropDataset(train_entries, train_transform)
    sampler = build_sampler(train_entries)

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, sampler=sampler,
                              num_workers=NUM_WORKERS, pin_memory=True)

    if val_entries:
        val_dataset = CropDataset(val_entries, val_transform)
        val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False,
                                num_workers=NUM_WORKERS, pin_memory=True)
    else:
        val_loader = None
        print("=== FULL-TRAIN MODE: no validation, saving periodic checkpoints ===")

    # Model
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    use_arcface = args.arcface

    model_name = args.model
    print(f"Using model: {model_name}")

    if use_arcface:
        print(f"Using ArcFace loss (margin={ARCFACE_MARGIN}, scale={ARCFACE_SCALE}, "
              f"embedding_dim={ARCFACE_EMBEDDING_DIM})")
        backbone = timm.create_model(model_name, pretrained=True, num_classes=num_classes)
        model = ArcFaceModel(backbone, num_classes, embedding_dim=ARCFACE_EMBEDDING_DIM)
        model = model.to(device)
        criterion = nn.CrossEntropyLoss(label_smoothing=LABEL_SMOOTHING)
    else:
        model = timm.create_model(model_name, pretrained=True, num_classes=num_classes)
        model = model.to(device)
        criterion = nn.CrossEntropyLoss(label_smoothing=LABEL_SMOOTHING)

    # Training
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=NUM_EPOCHS)

    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    best_acc = 0.0
    scaler = torch.amp.GradScaler(enabled=USE_AMP)

    for epoch in range(NUM_EPOCHS):
        # Train
        model.train()
        train_loss = 0
        train_correct = 0
        train_total = 0

        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)

            with torch.amp.autocast("cuda", enabled=USE_AMP):
                if use_arcface:
                    logits, _ = model(images, labels)
                else:
                    logits = model(images)
                loss = criterion(logits, labels)

            optimizer.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            train_loss += loss.item() * images.size(0)
            _, predicted = logits.max(1)
            train_correct += predicted.eq(labels).sum().item()
            train_total += labels.size(0)

        scheduler.step()

        train_acc = train_correct / train_total if train_total > 0 else 0
        avg_loss = train_loss / train_total if train_total > 0 else 0

        if val_loader is not None:
            # Validate
            model.eval()
            val_correct = 0
            val_total = 0

            with torch.no_grad():
                for images, labels in val_loader:
                    images, labels = images.to(device), labels.to(device)
                    with torch.amp.autocast("cuda", enabled=USE_AMP):
                        if use_arcface:
                            logits, _ = model(images)  # no labels = inference mode
                        else:
                            logits = model(images)
                    _, predicted = logits.max(1)
                    val_correct += predicted.eq(labels).sum().item()
                    val_total += labels.size(0)

            val_acc = val_correct / val_total if val_total > 0 else 0

            if val_acc > best_acc:
                best_acc = val_acc
                torch.save(model.state_dict(), SAVE_DIR / "best.pt")
                print(f"  → New best: {val_acc:.4f}")
        else:
            # Full-train: save periodically
            val_acc = 0
            if (epoch + 1) % 20 == 0 or epoch == NUM_EPOCHS - 1:
                torch.save(model.state_dict(), SAVE_DIR / "best.pt")
                print(f"  → Saved checkpoint (full-train, epoch {epoch+1})")

        print(f"Epoch {epoch+1}/{NUM_EPOCHS}  loss={avg_loss:.4f}  "
              f"train_acc={train_acc:.4f}  val_acc={val_acc:.4f}  "
              f"lr={scheduler.get_last_lr()[0]:.6f}")

    print(f"\nTraining complete! Best val accuracy: {best_acc:.4f}")
    print(f"Weights saved to {SAVE_DIR / 'best.pt'}")

    # Export to ONNX
    print("\nExporting to ONNX...")
    model.load_state_dict(torch.load(SAVE_DIR / "best.pt", map_location=device, weights_only=True))
    model.eval()

    dummy = torch.randn(1, 3, IMG_SIZE, IMG_SIZE).to(device)
    onnx_path = SAVE_DIR / "classifier.onnx"

    if use_arcface:
        # For ArcFace, export inference mode (no labels needed)
        # The forward without labels returns scaled cosine logits + embeddings
        torch.onnx.export(
            model, (dummy,), str(onnx_path),
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
            model, dummy, str(onnx_path),
            input_names=["input"],
            output_names=["output"],
            dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
            opset_version=17,
        )
    onnx_mb = onnx_path.stat().st_size / (1024 * 1024)
    print(f"Exported to {onnx_path} ({onnx_mb:.1f} MB)")


if __name__ == "__main__":
    main()
