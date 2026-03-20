"""Train DINOv2-ViT-S classifier for kNN + linear classification.

DINOv2 learns self-supervised features on diverse data — inherently more robust
to distribution shift than supervised EfficientNet. We fine-tune a linear head
on top of frozen/unfrozen DINOv2 features.

Setup:
    pip3 install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
    pip3 install timm==0.9.12 Pillow
    python3 extract_crops.py
    python3 train_dino_classifier.py [--letterbox] [--aggressive-aug]
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
from PIL import Image
import timm

DATA_DIR = Path(__file__).parent / "data"
CROPS_DIR = DATA_DIR / "crops"
SAVE_DIR = Path(__file__).parent / "runs" / "dino_classifier"

IMG_SIZE = 260  # Match EfficientNet-B2 input size for shared ONNX
BATCH_SIZE = 128  # DINOv2-ViT-S is larger, reduce batch
NUM_EPOCHS = 40  # Faster convergence with pretrained features
LR_HEAD = 1e-3  # Linear head LR
LR_BACKBONE = 1e-5  # Fine-tune backbone slowly
LABEL_SMOOTHING = 0.1
NUM_WORKERS = 8
REF_OVERSAMPLE = 10
USE_AMP = True
FREEZE_EPOCHS = 5  # Freeze backbone for first N epochs


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


class LetterboxRandomResizedCrop:
    """Letterbox + random scale augmentation."""
    def __init__(self, size, scale=(0.75, 1.0)):
        self.size = size
        self.scale = scale

    def __call__(self, img):
        import random
        w, h = img.size
        if w < 1 or h < 1:
            return Image.new("RGB", (self.size, self.size), (124, 116, 104))
        s = random.uniform(self.scale[0], self.scale[1])
        target = int(self.size / s)
        scale = min(target / w, target / h)
        nw, nh = int(w * scale), int(h * scale)
        resized = img.resize((nw, nh), Image.BILINEAR)
        canvas = Image.new("RGB", (target, target), (124, 116, 104))
        max_x = max(0, target - nw)
        max_y = max(0, target - nh)
        px = random.randint(0, max_x) if max_x > 0 else 0
        py = random.randint(0, max_y) if max_y > 0 else 0
        canvas.paste(resized, (px, py))
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


class DINOClassifier(nn.Module):
    """DINOv2-ViT-S with linear classification head."""
    def __init__(self, num_classes, model_name="vit_small_patch14_dinov2.lvd142m"):
        super().__init__()
        self.backbone = timm.create_model(model_name, pretrained=True, num_classes=0)
        embed_dim = self.backbone.embed_dim  # 384 for ViT-S
        self.head = nn.Sequential(
            nn.LayerNorm(embed_dim),
            nn.Linear(embed_dim, num_classes),
        )

    def forward(self, x):
        features = self.backbone(x)  # (B, embed_dim)
        logits = self.head(features)
        return logits, features

    def freeze_backbone(self):
        for param in self.backbone.parameters():
            param.requires_grad = False

    def unfreeze_backbone(self):
        for param in self.backbone.parameters():
            param.requires_grad = True


def build_datasets(manifest_path):
    """Build train/val datasets with oversampling for rare classes."""
    with open(manifest_path) as f:
        manifest = json.load(f)

    crops = manifest["crops"]
    num_classes = manifest["num_categories"]

    import random
    random.seed(42)

    by_cat = {}
    for c in crops:
        by_cat.setdefault(c["category_id"], []).append(c)

    train_entries = []
    val_entries = []

    for cat_id, entries in by_cat.items():
        ann_entries = [e for e in entries if e["source"] == "annotation"]
        ref_entries = [e for e in entries if e["source"] == "reference"]

        random.shuffle(ann_entries)
        split = max(1, int(len(ann_entries) * 0.9))
        train_ann = ann_entries[:split]
        val_ann = ann_entries[split:] if len(ann_entries) > 1 else []

        if len(train_ann) < 20 and ref_entries:
            oversample_factor = REF_OVERSAMPLE
        elif ref_entries:
            oversample_factor = 3
        else:
            oversample_factor = 0

        train_entries.extend(train_ann)
        train_entries.extend(ref_entries * oversample_factor)
        val_entries.extend(val_ann)

    print(f"Train: {len(train_entries)} samples, Val: {len(val_entries)} samples")
    print(f"Classes: {num_classes}")
    return train_entries, val_entries, num_classes


def build_sampler(entries):
    counts = Counter(e["category_id"] for e in entries)
    weights = [1.0 / math.sqrt(counts[e["category_id"]]) for e in entries]
    return WeightedRandomSampler(weights, len(weights), replacement=True)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--letterbox", action="store_true",
                        help="Use letterbox crops")
    parser.add_argument("--aggressive-aug", action="store_true",
                        help="Use aggressive domain augmentation")
    args = parser.parse_args()

    manifest_path = CROPS_DIR / "manifest.json"
    if not manifest_path.exists():
        print("Error: Run extract_crops.py first!")
        return

    train_entries, val_entries, num_classes = build_datasets(manifest_path)

    # Augmentation
    if args.aggressive_aug:
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

    if args.letterbox:
        print("Using LETTERBOX transforms")
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
        print("Using SQUASH transforms")
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
    val_ds = CropDataset(val_entries, val_transform)
    sampler = build_sampler(train_entries)

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, sampler=sampler,
                              num_workers=NUM_WORKERS, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False,
                            num_workers=NUM_WORKERS, pin_memory=True)

    # Model
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Loading DINOv2-ViT-S...")
    model = DINOClassifier(num_classes).to(device)
    print(f"Backbone embed_dim: {model.backbone.embed_dim}")

    criterion = nn.CrossEntropyLoss(label_smoothing=LABEL_SMOOTHING)
    scaler = torch.amp.GradScaler(enabled=USE_AMP)
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    best_acc = 0.0

    # Phase 1: Freeze backbone, train head only
    model.freeze_backbone()
    head_params = list(model.head.parameters())
    optimizer = torch.optim.AdamW(head_params, lr=LR_HEAD, weight_decay=0.01)

    for epoch in range(NUM_EPOCHS):
        # Unfreeze backbone after FREEZE_EPOCHS
        if epoch == FREEZE_EPOCHS:
            print(f"\n=== Unfreezing backbone at epoch {epoch+1} ===")
            model.unfreeze_backbone()
            optimizer = torch.optim.AdamW([
                {"params": model.backbone.parameters(), "lr": LR_BACKBONE},
                {"params": model.head.parameters(), "lr": LR_HEAD * 0.1},
            ], weight_decay=0.01)

        model.train()
        train_loss = 0
        train_correct = 0
        train_total = 0

        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)

            with torch.amp.autocast("cuda", enabled=USE_AMP):
                logits, _ = model(images)
                loss = criterion(logits, labels)

            optimizer.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            train_loss += loss.item() * images.size(0)
            _, predicted = logits.max(1)
            train_correct += predicted.eq(labels).sum().item()
            train_total += labels.size(0)

        # Validate
        model.eval()
        val_correct = 0
        val_total = 0

        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                with torch.amp.autocast("cuda", enabled=USE_AMP):
                    logits, _ = model(images)
                _, predicted = logits.max(1)
                val_correct += predicted.eq(labels).sum().item()
                val_total += labels.size(0)

        train_acc = train_correct / train_total if train_total > 0 else 0
        val_acc = val_correct / val_total if val_total > 0 else 0
        avg_loss = train_loss / train_total if train_total > 0 else 0

        phase = "head-only" if epoch < FREEZE_EPOCHS else "full"
        print(f"Epoch {epoch+1}/{NUM_EPOCHS} [{phase}]  loss={avg_loss:.4f}  "
              f"train_acc={train_acc:.4f}  val_acc={val_acc:.4f}")

        if val_acc > best_acc:
            best_acc = val_acc
            torch.save(model.state_dict(), SAVE_DIR / "best.pt")
            print(f"  → New best: {val_acc:.4f}")

    print(f"\nTraining complete! Best val accuracy: {best_acc:.4f}")
    print(f"Weights saved to {SAVE_DIR / 'best.pt'}")

    # Export to ONNX
    print("\nExporting to ONNX...")
    model.load_state_dict(torch.load(SAVE_DIR / "best.pt", map_location=device, weights_only=True))
    model.eval()

    dummy = torch.randn(1, 3, IMG_SIZE, IMG_SIZE).to(device)
    onnx_path = SAVE_DIR / "dino_classifier.onnx"
    torch.onnx.export(
        model, dummy, str(onnx_path),
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


if __name__ == "__main__":
    main()
