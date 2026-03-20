"""Package run.py + best.onnx into submission.zip."""

import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
WEIGHTS = ROOT / "model.onnx"


def main():
    if not WEIGHTS.exists():
        print("Error: best.onnx not found. Export model first.")
        return

    output = ROOT / "submission.zip"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(ROOT / "run.py", "run.py")
        zf.write(WEIGHTS, "model.onnx")

    size_mb = output.stat().st_size / (1024 * 1024)
    print(f"Created {output} ({size_mb:.1f} MB)")

    if size_mb > 420:
        print("WARNING: submission.zip exceeds 420MB limit!")
    else:
        print("Size OK (< 420MB)")


if __name__ == "__main__":
    main()
