"""Sweep run.py hyperparameters and compare competition scores.

Modifies run.py constants, runs validation, and collects results.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
RUN_PY = ROOT / "run.py"

CONFIGS = [
    ("baseline",       {"USE_SOFT_NMS": "False", "USE_TTA": "False", "SCORE_CLS_POWER": "1.0"}),
    ("tta_only",       {"USE_SOFT_NMS": "False", "USE_TTA": "True",  "SCORE_CLS_POWER": "1.0"}),
    ("tta+sqrt",       {"USE_SOFT_NMS": "False", "USE_TTA": "True",  "SCORE_CLS_POWER": "0.5"}),
    ("tta+pow07",      {"USE_SOFT_NMS": "False", "USE_TTA": "True",  "SCORE_CLS_POWER": "0.7"}),
    ("softnms_only",   {"USE_SOFT_NMS": "True",  "USE_TTA": "False", "SCORE_CLS_POWER": "1.0",
                        "SOFT_NMS_THRESH": "0.05"}),
    ("softnms+tta",    {"USE_SOFT_NMS": "True",  "USE_TTA": "True",  "SCORE_CLS_POWER": "1.0",
                        "SOFT_NMS_THRESH": "0.05"}),
]


def set_config(content, config):
    """Replace config values in run.py source."""
    for key, value in config.items():
        pattern = rf"^{key}\s*=\s*.*$"
        replacement = f"{key} = {value}"
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    return content


def extract_scores(output):
    """Extract scores from validate.py output."""
    det = cls = score = None
    for line in output.split("\n"):
        if "Detection mAP@0.5" in line:
            m = re.search(r":\s+([\d.]+)", line)
            if m:
                det = float(m.group(1))
        elif "Classification mAP@0.5" in line:
            m = re.search(r":\s+([\d.]+)", line)
            if m:
                cls = float(m.group(1))
        elif "COMPETITION SCORE" in line:
            m = re.search(r":\s+([\d.]+)", line)
            if m:
                score = float(m.group(1))
    return det, cls, score


def main():
    original = RUN_PY.read_text()
    results = []

    for name, config in CONFIGS:
        print(f"\n{'='*60}")
        print(f"Testing: {name}")
        print(f"Config: {config}")
        print(f"{'='*60}")

        modified = set_config(original, config)
        RUN_PY.write_text(modified)

        result = subprocess.run(
            ["python3", str(ROOT / "validate.py")],
            capture_output=True, text=True, timeout=600
        )
        output = result.stdout + result.stderr

        det, cls, score = extract_scores(output)
        # Count predictions
        pred_count = None
        m = re.search(r"Generated (\d+) predictions", output)
        if m:
            pred_count = int(m.group(1))

        results.append((name, det, cls, score, pred_count))
        print(f"  Det={det}, Cls={cls}, Score={score}, Preds={pred_count}")

    # Restore original
    RUN_PY.write_text(original)

    # Print comparison
    print(f"\n\n{'='*80}")
    print(f"{'Config':<20} {'Det mAP':<10} {'Cls mAP':<10} {'Score':<10} {'Preds':<8} {'vs baseline'}")
    print(f"{'-'*80}")
    baseline_score = results[0][3] if results[0][3] else 0
    for name, det, cls, score, preds in results:
        delta = (score - baseline_score) if score and baseline_score else 0
        sign = "+" if delta >= 0 else ""
        print(f"{name:<20} {det or 0:<10.4f} {cls or 0:<10.4f} {score or 0:<10.4f} {preds or 0:<8} {sign}{delta:.4f}")


if __name__ == "__main__":
    main()
