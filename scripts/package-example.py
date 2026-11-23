"""Package the example without executing it or installing it automatically."""
from pathlib import Path
import sys
import zipfile

source = Path(__file__).resolve().parents[1] / "examples/counter"
output = Path(sys.argv[1])
output.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    for name in ("manifest.json", "main.py"):
        archive.write(source / name, name)
print(output)
