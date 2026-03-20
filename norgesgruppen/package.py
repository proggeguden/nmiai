"""Package submission: run.py + detector.onnx + classifier.onnx + multiclass_detector.onnx."""

import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
DETECTOR = ROOT / "detector.onnx"
CLASSIFIER = ROOT / "classifier.onnx"
MULTICLASS = ROOT / "multiclass_detector.onnx"
EMBEDDINGS = ROOT / "embeddings.npy"


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
        if MULTICLASS.exists():
            zf.write(MULTICLASS, "multiclass_detector.onnx")
        elif EMBEDDINGS.exists():
            zf.write(EMBEDDINGS, "embeddings.npy")

    size_mb = output.stat().st_size / (1024 * 1024)
    print(f"Created {output} ({size_mb:.1f} MB)")

    files = [("detector.onnx", DETECTOR), ("classifier.onnx", CLASSIFIER)]
    if MULTICLASS.exists():
        files.append(("multiclass_detector.onnx", MULTICLASS))
    elif EMBEDDINGS.exists():
        files.append(("embeddings.npy", EMBEDDINGS))

    total = 0
    for name, path in files:
        mb = path.stat().st_size / (1024 * 1024)
        total += mb
        print(f"  {name}: {mb:.1f} MB")

    print(f"  total weights:   {total:.1f} MB {'OK' if total < 420 else 'OVER LIMIT!'}")
    print(f"  weight files:    {len(files)}/3 {'OK' if len(files) <= 3 else 'OVER LIMIT!'}")

    if size_mb > 420:
        print("WARNING: submission.zip exceeds 420MB limit!")


if __name__ == "__main__":
    main()
