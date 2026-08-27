#!/usr/bin/env python3
"""Turn tagged songs into backlog.json -- a board of Ultimate Guitar search links.

Ranks by guitar value, drops anything already on a hand-curated board, and
balances the picks across the growth edges so it isn't 40 fingerstyle tunes.

Usage:  python3 tools/3_build.py [--top 40] [--min-guitar 3] [--per-edge 12]
"""
import argparse, re, sys, time, urllib.parse
import requests
from common import ROOT, LIBRARY, TAGS, BACKLOG, DATA, read_json, write_json

UG_CACHE = ROOT / "ug-cache.json"      # gitignored: search -> has-tabs, so re-runs are quiet
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"}

UG = "https://www.ultimate-guitar.com/search.php?search_type=title&value="
EDGES = {"finger": "fingerstyle", "pick": "pick", "electric": "electric",
         "slide": "slide", "none": "—"}


def norm(s):
    """Loose key for 'is this already on a board' -- ignores case, punctuation,
    and parenthetical suffixes like '(Dink's Song)' or '- Remastered 2011'."""
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s.lower())
    s = re.split(r" - (remaster|live|mono|stereo|single|radio)", s)[0]
    return re.sub(r"[^a-z0-9]+", "", s)


# Spotify titles carry release cruft ("- Live from Spotify SXSW 2014", "- Remastered
# 2011", "(feat. X)") that finds nothing on Ultimate Guitar and reads badly on the
# board. Strip suffixes only -- parentheticals mid-title are often part of the real
# name ("Don't Mistreat Nobody (Cause You Got a Few Dimes)").
JUNK = re.compile(r"\s+-\s+(?:live|remaster|mono|stereo|single|radio|demo|alternate|"
                  r"bonus|previously|acoustic|instrumental|edit\b|.*?\b"
                  r"(?:version|take|mix|edit|session|remaster)\b).*$", re.I)
FEAT = re.compile(r"\s*[\(\[]feat\.[^)\]]*[\)\]]", re.I)


def clean_title(t):
    t = FEAT.sub("", t)
    t = JUNK.sub("", t)
    return t.strip(" -\u2013")


def slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")[:48]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=40, help="max songs on the board")
    ap.add_argument("--min-guitar", type=int, default=3, help="minimum g score to qualify")
    ap.add_argument("--per-edge", type=int, default=12, help="cap per growth edge, for balance")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip checking that each UG search actually returns tabs")
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

    # Round-robin across edges so every guitar gets something to do. Each pick is
    # checked against Ultimate Guitar first: plenty of obscure blues sides have no
    # tab at all, and a dead link is worse than the next song down the list.
    ug_cache = read_json(UG_CACHE, {}) or {}

    def has_tabs(artist, title):
        q = f"{artist} {title}"
        if q in ug_cache:
            return ug_cache[q]
        try:
            r = requests.get(UG + urllib.parse.quote_plus(q), headers=UA, timeout=30)
            ok = r.status_code == 200 and "tabs.ultimate-guitar.com/tab" in r.text.lower()
        except requests.RequestException:
            ok = True                      # network trouble: don't silently drop a good song
        ug_cache[q] = ok
        write_json(UG_CACHE, ug_cache)
        time.sleep(1.5)                    # be a polite guest
        return ok

    buckets = {}
    for t, tag in cands:
        buckets.setdefault(tag.get("e") or "none", []).append((t, tag))

    order = ["finger", "pick", "electric", "slide", "none"]
    picked, taken, checked, skipped = [], {e: 0 for e in order}, 0, 0
    if not a.no_verify:
        print(f"Checking picks against Ultimate Guitar (~1.5s each)...")
    while len(picked) < a.top and any(buckets.get(e) for e in order):
        progressed = False
        for e in order:
            if len(picked) >= a.top or not buckets.get(e) or taken[e] >= a.per_edge:
                continue
            while buckets[e]:
                t, tag = buckets[e].pop(0)
                if a.no_verify:
                    break
                checked += 1
                if has_tabs(t["artist"].split(",")[0], clean_title(t["title"])):
                    break
                skipped += 1
            else:
                continue
            picked.append((t, tag)); taken[e] += 1; progressed = True
        if not progressed:
            break
    if not a.no_verify:
        print(f"  checked {checked}, skipped {skipped} with no tabs on UG")
    picked.sort(key=lambda x: (-x[1]["score"], x[1].get("d") or 3))

    songs = []
    for t, tag in picked:
        title = clean_title(t["title"])
        q = urllib.parse.quote_plus(f'{t["artist"].split(",")[0]} {title}')
        songs.append({
            "id": "bl-" + slug(f'{t["artist"]}-{title}'),
            "parts": [{"t": title, "u": UG + q}],
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
              f'{t["artist"].split(",")[0]} - {clean_title(t["title"])}  ({tag.get("w")})')


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tools"))
    main()
