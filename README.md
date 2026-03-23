# NM i AI 2026

Competition entry for [NM i AI 2026](https://app.ainm.no) — the Norwegian AI Championship.

**Team:** Løkka Language Models | **Overall: 86.0 pts, #42**

## Results

| Task | Score | Rank | Normalized |
|------|-------|------|------------|
| **NorgesGruppen Data** | 0.7095 mAP | **#5** | 99.8 |
| **Tripletex** | 60.61 pts | #124 | 58.1 |
| **Astar Island** | 266.6 pts | **#1** | 100.0 |
| **Overall** | — | **#42** | 86.0 |

## Tasks

### NorgesGruppen Data — Grocery Product Detection

Detect and classify grocery products on store shelves. Scored as 70% detection mAP@0.5 + 30% classification mAP@0.5 across 356 product categories.

**Approach:** Two-stage pipeline with WBF ensemble.
1. YOLOv8l single-class detector (imgsz=1280) for bounding box proposals
2. Dual-backbone classifier (EfficientNet-B2 + DINOv2-ViT-S) for product identification
3. YOLOv8m multi-class detector fused via Weighted Boxes Fusion
4. kNN embedding retrieval (DINOv2 features) for rare category support
5. TTA (4 augments) with letterbox aspect-ratio preservation

### Tripletex — AI Accounting Agent

AI agent that solves accounting tasks via the Tripletex API. Receives natural-language task descriptions and executes multi-step API workflows (invoices, vouchers, payroll, travel expenses, etc.).

**Approach:** LLM-based agent with structured planning, API discovery, and self-healing error recovery.

### Astar Island — Norse World Prediction

Predict hidden parameters of a Norse-themed simulated world across sequential rounds. New ground truth data is revealed each round.

**Approach:** ML ensemble with engineered features, trained on accumulating ground truth. Conditional transition modeling with snapshot ensembles.

## Tech Stack

- Python, PyTorch, ultralytics (YOLOv8), timm, ONNX Runtime
- GCP VMs with L4 GPUs for training
- Claude Code for development assistance
