"""Package submission: run.py + _knn_blob.txt + detector.onnx + classifier.onnx + multiclass_detector.onnx."""

import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
DETECTOR = ROOT / "detector.onnx"
CLASSIFIER = ROOT / "classifier.onnx"
MULTICLASS = ROOT / "multiclass_detector.onnx"
KNN_BLOB = ROOT / "_knn_data.json"


def main():
    for f in [DETECTOR, CLASSIFIER]:
        if not f.exists():
            print(f"Error: {f.name} not found!")
            return

    output = ROOT / "submission.zip"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(ROOT / "run.py", "run.py")
        if KNN_BLOB.exists():
            zf.write(KNN_BLOB, "_knn_data.json")
        zf.write(DETECTOR, "detector.onnx")
        zf.write(CLASSIFIER, "classifier.onnx")
        if MULTICLASS.exists():
            zf.write(MULTICLASS, "multiclass_detector.onnx")

    size_mb = output.stat().st_size / (1024 * 1024)
    print(f"Created {output} ({size_mb:.1f} MB)")

    weight_files = [("detector.onnx", DETECTOR), ("classifier.onnx", CLASSIFIER)]
    if MULTICLASS.exists():
        weight_files.append(("multiclass_detector.onnx", MULTICLASS))

    total = 0
    for name, path in weight_files:
        mb = path.stat().st_size / (1024 * 1024)
        total += mb
        print(f"  {name}: {mb:.1f} MB")

    if KNN_BLOB.exists():
        blob_mb = KNN_BLOB.stat().st_size / (1024 * 1024)
        total += blob_mb
        print(f"  _knn_data.json: {blob_mb:.1f} MB (embedded kNN data)")

    print(f"  total uncompressed: {total:.1f} MB {'OK' if total < 420 else 'OVER LIMIT!'}")
    print(f"  weight files:       {len(weight_files)}/3 {'OK' if len(weight_files) <= 3 else 'OVER LIMIT!'}")

    if size_mb > 420:
        print("WARNING: submission.zip exceeds 420MB limit!")


if __name__ == "__main__":
    main()
