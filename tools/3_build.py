#!/usr/bin/env python3
"""Turn tagged songs into backlog.json -- a board of Ultimate Guitar search links.

Ranks by guitar value, drops anything already on a hand-curated board, and
balances the picks across the growth edges so it isn't 40 fingerstyle tunes.

Usage:  python3 tools/3_build.py [--top 40] [--min-guitar 3] [--per-edge 12]
"""
import argparse, re, sys, time, urllib.parse
from common import ROOT, LIBRARY, TAGS, BACKLOG, DATA, read_json, write_json

UG = "https://www.ultimate-guitar.com/search.php?search_type=title&value="
EDGES = {"finger": "fingerstyle", "pick": "pick", "electric": "electric",
         "slide": "slide", "none": "—"}


def norm(s):
    """Loose key for 'is this already on a board' -- ignores case, punctuation,
    and parenthetical suffixes like '(Dink's Song)' or '- Remastered 2011'."""
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s.lower())
    s = re.split(r" - (remaster|live|mono|stereo|single|radio)", s)[0]
    return re.sub(r"[^a-z0-9]+", "", s)


def slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")[:48]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=40, help="max songs on the board")
    ap.add_argument("--min-guitar", type=int, default=3, help="minimum g score to qualify")
    ap.add_argument("--per-edge", type=int, default=12, help="cap per growth edge, for balance")
    a = ap.parse_args()

    lib = read_json(LIBRARY) or {"tracks": []}
    tags = read_json(TAGS, {}) or {}
    data = read_json(DATA) or {"boards": []}
    if not tags:
        raise SystemExit("No tags.json -- run tools/2_tag.py first.")

    # Everything already curated by hand, so the backlog never repeats the boards.
    have = set()
    for b in data.get("boards", []):
        for s in b.get("songs", []):
            for p in s.get("parts", []):
                have.add(norm(p["t"]))

    seen, cands = set(), []
    for t in lib["tracks"]:
        tag = tags.get(t["id"])
        if not tag or not isinstance(tag.get("g"), int):
            continue
        if tag["g"] < a.min_guitar:
            continue
        k = norm(t["title"])
        if k in have or k in seen:        # dedupe re-releases and live versions
            continue
        seen.add(k)
        tag["score"] = tag["g"] * 2 + (tag.get("f") or 0)
        cands.append((t, tag))

    cands.sort(key=lambda x: (-x[1]["score"], x[1].get("d") or 3))

    # Round-robin across edges so every guitar gets something to do.
    buckets, picked = {}, []
    for t, tag in cands:
        e = tag.get("e") or "none"
        b = buckets.setdefault(e, [])
        if len(b) < a.per_edge:
            b.append((t, tag))
    order = ["finger", "pick", "electric", "slide", "none"]
    while len(picked) < a.top and any(buckets.get(e) for e in order):
        for e in order:
            if buckets.get(e) and len(picked) < a.top:
                picked.append(buckets[e].pop(0))
    picked.sort(key=lambda x: (-x[1]["score"], x[1].get("d") or 3))

    songs = []
    for t, tag in picked:
        q = urllib.parse.quote_plus(f'{t["artist"].split(",")[0]} {t["title"]}')
        songs.append({
            "id": "bl-" + slug(f'{t["artist"]}-{t["title"]}'),
            "parts": [{"t": t["title"], "u": UG + q}],
            "small": f'{t["artist"].split(",")[0]} — {tag.get("w") or ""}'.rstrip(" —"),
            "chip": {"t": EDGES.get(tag.get("e"), "—"), "c": "later"},
        })

    counts = {e: sum(1 for _, g in picked if (g.get("e") or "none") == e) for e in order}
    write_json(BACKLOG, {
        "meta": {
            "generated": time.strftime("%Y-%m-%d"),
            "liked": len(lib["tracks"]), "tagged": len(tags),
            "qualified": len(cands), "shown": len(songs),
            "by_edge": {k: v for k, v in counts.items() if v},
        },
        "board": {
            "emoji": "🎧",
            "title": "From your Spotify",
            "sub": "auto-suggested from liked songs · titles open an Ultimate Guitar search",
            "songs": songs,
        },
    })
    print(f"Wrote {BACKLOG.name}: {len(songs)} of {len(cands)} qualifying songs.")
    print("  by edge: " + " · ".join(f"{k} {v}" for k, v in counts.items() if v))
    print("\nTop picks:")
    for t, tag in picked[:12]:
        print(f'  g{tag["g"]} f{tag.get("f")} d{tag.get("d")} [{tag.get("e")}]  '
              f'{t["artist"].split(",")[0]} - {t["title"]}  ({tag.get("w")})')


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tools"))
    main()
