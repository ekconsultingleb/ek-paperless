from pathlib import Path
import sys

_GIANNI_SRC: str | None = None


def _gianni_src_dir(root: Path) -> Path:
    return root / "gianni" / "src"


def _is_shadow_supa_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    if "gianni/src" in normalized:
        return False
    return "supa import" in normalized or normalized.endswith("/supa_import")


def _purge_shadow_supa_import(correct_src: str) -> None:
    correct = correct_src.replace("\\", "/")
    for name in list(sys.modules):
        if name != "supa_import" and not name.startswith("supa_import."):
            continue
        mod = sys.modules.get(name)
        mod_file = getattr(mod, "__file__", "") or ""
        if not mod_file:
            continue
        mod_path = mod_file.replace("\\", "/")
        if correct not in mod_path:
            del sys.modules[name]


def ensure_supa_env_from_secrets() -> None:
    import os

    import streamlit as st

    mapping = {
        "SUPABASE_URL": "url",
        "SUPABASE_KEY": "key",
        "host": "host",
        "name": "dbname",
        "user": "user",
        "password": "password",
        "port": "port",
    }
    for secret_key, env_key in mapping.items():
        if os.getenv(env_key):
            continue
        val = st.secrets.get(secret_key)
        if val:
            os.environ[env_key] = str(val)


def bootstrap_src() -> bool:
    global _GIANNI_SRC

    root = Path(__file__).resolve().parent
    src = _gianni_src_dir(root)
    if not src.is_dir():
        return False

    src_str = str(src)
    _GIANNI_SRC = src_str

    sys.path[:] = [p for p in sys.path if not _is_shadow_supa_path(p)]

    if src_str in sys.path:
        sys.path.remove(src_str)
    sys.path.insert(0, src_str)

    _purge_shadow_supa_import(src_str)
    return True
