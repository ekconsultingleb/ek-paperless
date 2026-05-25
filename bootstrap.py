from pathlib import Path
import sys


def bootstrap_src():
    root = Path(__file__).resolve().parent
    src = root / "gianni" / "src"

    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    return root