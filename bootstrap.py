from pathlib import Path
import sys


def bootstrap_src():
    root = Path(__file__).resolve().parent
    src = root / "gianni" / "src"

    if not src.is_dir():
        return False

    src_str = str(src)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)

    return True