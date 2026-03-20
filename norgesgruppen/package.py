"""Package two-stage submission: run.py + detector.onnx + classifier.onnx."""

import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
DETECTOR = ROOT / "detector.onnx"
CLASSIFIER = ROOT / "classifier.onnx"


def main():
    for f in [DETECTOR, CLASSIFIER]:
        if not f.exists():
            print(f"Error: {f.name} not found!")
            return

    output = ROOT / "submission.zip"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(ROOT / "run.py", "run.py")
        zf.write(DETECTOR, "detector.onnx")
        zf.write(CLASSIFIER, "classifier.onnx")

    size_mb = output.stat().st_size / (1024 * 1024)
    print(f"Created {output} ({size_mb:.1f} MB)")

    # Check limits
    det_mb = DETECTOR.stat().st_size / (1024 * 1024)
    cls_mb = CLASSIFIER.stat().st_size / (1024 * 1024)
    total_weight_mb = det_mb + cls_mb
    print(f"  detector.onnx: {det_mb:.1f} MB")
    print(f"  classifier.onnx: {cls_mb:.1f} MB")
    print(f"  total weights: {total_weight_mb:.1f} MB {'OK' if total_weight_mb < 420 else 'OVER LIMIT!'}")
    print(f"  zip files: 3 (run.py + 2 weights) {'OK' if True else ''}")

    if size_mb > 420:
        print("WARNING: submission.zip exceeds 420MB limit!")


if __name__ == "__main__":
    main()
