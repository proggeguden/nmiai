"""Sweep run.py parameters using stratified validation (330 categories covered).

More representative than the old 25-image val split.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
RUN_PY = ROOT / "run.py"

CONFIGS = [
    ("current",        {"DET_CONF": "0.10", "WBF_TWO_STAGE_WEIGHT": "0.6", "WBF_MULTICLASS_WEIGHT": "0.4", "USE_TTA": "True"}),
    ("conf_015",       {"DET_CONF": "0.15", "WBF_TWO_STAGE_WEIGHT": "0.6", "WBF_MULTICLASS_WEIGHT": "0.4", "USE_TTA": "True"}),
    ("conf_020",       {"DET_CONF": "0.20", "WBF_TWO_STAGE_WEIGHT": "0.6", "WBF_MULTICLASS_WEIGHT": "0.4", "USE_TTA": "True"}),
    ("wbf_50_50",      {"DET_CONF": "0.10", "WBF_TWO_STAGE_WEIGHT": "0.5", "WBF_MULTICLASS_WEIGHT": "0.5", "USE_TTA": "True"}),
    ("wbf_70_30",      {"DET_CONF": "0.10", "WBF_TWO_STAGE_WEIGHT": "0.7", "WBF_MULTICLASS_WEIGHT": "0.3", "USE_TTA": "True"}),
    ("no_tta",         {"DET_CONF": "0.10", "WBF_TWO_STAGE_WEIGHT": "0.6", "WBF_MULTICLASS_WEIGHT": "0.4", "USE_TTA": "False"}),
    ("no_wbf",         {"DET_CONF": "0.10", "USE_WBF": "False", "USE_TTA": "True"}),
    ("conf015_wbf5050",{"DET_CONF": "0.15", "WBF_TWO_STAGE_WEIGHT": "0.5", "WBF_MULTICLASS_WEIGHT": "0.5", "USE_TTA": "True"}),
]


def set_config(content, config):
    for key, value in config.items():
        pattern = rf"^{key}\s*=\s*.*$"
        replacement = f"{key} = {value}"
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    return content


def extract_scores(output):
    det = cls = score = None
    for line in output.split("\n"):
        if "Detection mAP@0.5" in line:
            m = re.search(r":\s+([\d.]+)", line)
            if m: det = float(m.group(1))
        elif "Classification mAP@0.5" in line:
            m = re.search(r":\s+([\d.]+)", line)
            if m: cls = float(m.group(1))
        elif "COMPETITION SCORE" in line:
            m = re.search(r":\s+([\d.]+)", line)
            if m: score = float(m.group(1))
    return det, cls, score


def main():
    original = RUN_PY.read_text()
    results = []

    for name, config in CONFIGS:
        print(f"\n{'='*60}")
        print(f"Testing: {name} — {config}")
        print(f"{'='*60}")

        modified = set_config(original, config)
        RUN_PY.write_text(modified)

        result = subprocess.run(
            ["python3", str(ROOT / "stratified_validate.py")],
            capture_output=True, text=True, timeout=900
        )
        output = result.stdout + result.stderr
        det, cls, score = extract_scores(output)

        pred_count = None
        m = re.search(r"Generated (\d+) predictions", output)
        if m: pred_count = int(m.group(1))

        results.append((name, det, cls, score, pred_count))
        print(f"  Det={det}, Cls={cls}, Score={score}, Preds={pred_count}")

    # Restore original
    RUN_PY.write_text(original)

    # Print comparison
    print(f"\n\n{'='*90}")
    print(f"{'Config':<20} {'Det mAP':<10} {'Cls mAP':<10} {'Score':<10} {'Preds':<8} {'vs current'}")
    print(f"{'-'*90}")
    baseline_score = results[0][3] if results[0][3] else 0
    for name, det, cls, score, preds in results:
        delta = (score - baseline_score) if score and baseline_score else 0
        sign = "+" if delta >= 0 else ""
        print(f"{name:<20} {det or 0:<10.4f} {cls or 0:<10.4f} {score or 0:<10.4f} {preds or 0:<8} {sign}{delta:.4f}")


if __name__ == "__main__":
    main()
