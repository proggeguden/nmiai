"""Train EfficientNet-B2 classifier on annotation crops + reference images.

Setup:
    pip3 install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
    pip3 install timm==0.9.12 Pillow
    python3 extract_crops.py   # must run first
    python3 train_classifier.py
"""

import json
import math
from collections import Counter
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler
from torchvision import transforms
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


def build_datasets(manifest_path):
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
    manifest_path = CROPS_DIR / "manifest.json"
    if not manifest_path.exists():
        print("Error: Run extract_crops.py first!")
        return

    train_entries, val_entries, num_classes = build_datasets(manifest_path)

    # Transforms
    train_transform = transforms.Compose([
        transforms.RandomResizedCrop(IMG_SIZE, scale=(0.7, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.05),
        transforms.RandomRotation(15),
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
    model = timm.create_model("efficientnet_b2", pretrained=True, num_classes=num_classes)
    model = model.to(device)

    # Training
    criterion = nn.CrossEntropyLoss(label_smoothing=LABEL_SMOOTHING)
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
                outputs = model(images)
                loss = criterion(outputs, labels)

            optimizer.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            train_loss += loss.item() * images.size(0)
            _, predicted = outputs.max(1)
            train_correct += predicted.eq(labels).sum().item()
            train_total += labels.size(0)

        scheduler.step()

        # Validate
        model.eval()
        val_correct = 0
        val_total = 0

        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                with torch.amp.autocast("cuda", enabled=USE_AMP):
                    outputs = model(images)
                _, predicted = outputs.max(1)
                val_correct += predicted.eq(labels).sum().item()
                val_total += labels.size(0)

        train_acc = train_correct / train_total if train_total > 0 else 0
        val_acc = val_correct / val_total if val_total > 0 else 0
        avg_loss = train_loss / train_total if train_total > 0 else 0

        print(f"Epoch {epoch+1}/{NUM_EPOCHS}  loss={avg_loss:.4f}  "
              f"train_acc={train_acc:.4f}  val_acc={val_acc:.4f}  "
              f"lr={scheduler.get_last_lr()[0]:.6f}")

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
    onnx_path = SAVE_DIR / "classifier.onnx"
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
