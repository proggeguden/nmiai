"""Package run.py + best.pt into submission.zip."""

import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
WEIGHTS = ROOT / "best.pt"


def main():
    if not WEIGHTS.exists():
        # Also check runs directory
        alt = ROOT / "runs" / "detect_mvp" / "weights" / "best.pt"
        if alt.exists():
            import shutil
            shutil.copy2(alt, WEIGHTS)
            print(f"Copied weights from {alt}")
        else:
            print(f"Error: best.pt not found. Train first.")
            return

    output = ROOT / "submission.zip"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(ROOT / "run.py", "run.py")
        zf.write(WEIGHTS, "best.pt")

    size_mb = output.stat().st_size / (1024 * 1024)
    print(f"Created {output} ({size_mb:.1f} MB)")

    if size_mb > 500:
        print("WARNING: submission.zip exceeds 500MB limit!")
    else:
        print("Size OK (< 500MB)")


if __name__ == "__main__":
    main()
