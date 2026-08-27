"""Shared helpers: .env loading and paths. No third-party deps beyond requests."""
import os, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "library.json"      # gitignored: full liked-songs dump
TAGS    = ROOT / "tags.json"         # gitignored: tag cache, keyed by track id
ARTISTS = ROOT / "artists.json"      # gitignored: artist -> genres cache
BACKLOG = ROOT / "backlog.json"      # committed: the curated output
DATA    = ROOT / "data.json"         # the hand-curated boards


def load_env():
    """Read .env into os.environ without clobbering real env vars."""
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


def need(key, hint):
    load_env()
    v = os.environ.get(key)
    if not v:
        raise SystemExit(f"Missing {key}.\n  {hint}\n  Put it in {ROOT/'.env'} (gitignored).")
    return v


def read_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n")
