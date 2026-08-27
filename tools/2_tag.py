#!/usr/bin/env python3
"""Tag liked songs for guitar-learning value using Claude Haiku, cheaply.

Cost control, in order of how much it saves:
  1. Cache by track id -- re-runs only pay for songs added since last time.
  2. Batching + terse keys -- ~40 songs per call, single-letter JSON fields.
  3. Prompt caching on the rubric -- the big constant block is charged once.
  4. Dedupe + skip already-curated songs -- free, before any API call.
  5. Genre prefilter -- only bites if library.json actually has genres, which
     Spotify no longer provides to new apps. Kept for if that ever changes.

Usage:  python3 tools/2_tag.py [--limit N] [--batch 40] [--dry-run]
"""
import argparse, json, re, sys, time
import requests
from common import ROOT, LIBRARY, TAGS, DATA, need, read_json, write_json

MODEL = "claude-haiku-4-5-20251001"
PRICE_IN, PRICE_OUT = 1.00 / 1e6, 5.00 / 1e6      # USD per token
PRICE_CACHE_W, PRICE_CACHE_R = 1.25 / 1e6, 0.10 / 1e6

# Genres where a guitar tab is essentially never the point. A track is dropped
# only if it hits one of these AND nothing in KEEP -- artists carry several tags.
DROP = re.compile(r"\b(edm|techno|house|trance|dubstep|drum and bass|electro|"
                  r"hip hop|rap|trap|grime|drill|reggaeton|k-pop|"
                  r"ambient|drone|classical|opera|orchestral|choral|"
                  r"disco|funk carioca|dancehall|synthwave|vaporwave)\b", re.I)
KEEP = re.compile(r"\b(folk|blues|country|americana|bluegrass|singer-songwriter|"
                  r"rock|acoustic|fingerstyle|delta|slide|roots|alt-country|"
                  r"grunge|indie|punk|soul|r&b|jazz|swing|ragtime|gospel)\b", re.I)

RUBRIC = """You rate songs for a specific returning guitarist. Be strict and honest.

THE PLAYER
Strong fingerstyle background -- American Primitive; Jack Rose's "Kensington Blues"
was his peak. Folk-blues repertoire: Dave Van Ronk, Rev. Gary Davis, Nico, Robert
Johnson, Beatles. Returning after a long break, so technique is rusty but the
ceiling is high. Three guitars with jobs: Martin (standard tuning, fingerstyle),
Epiphone Dove (open D, slide only), Strat through a Bassbreaker (electric blues).
GROWTH EDGES he actively wants to work on: flatpick technique, electric/blues lead
vocabulary, and slide. He does NOT need more easy open-chord strumming.

FOR EACH SONG, RATE
 g  0-5  guitar-forward: is guitar the thing you'd actually learn here?
         0 = programmed/vocal-led with no real guitar part, 5 = the guitar IS the song
 f  0-5  fit: does this suit his taste and repertoire direction?
 e  which growth edge it serves, one of:
         "finger" (fingerstyle/folk-blues) | "pick" (flatpicking/strumming technique)
         | "electric" (blues lead, riffs, electric vocabulary) | "slide" (open tunings,
         bottleneck) | "none"
 d  1-5  difficulty for a rusty but formerly advanced player (1 trivial, 5 a project)
 w  why, MAXIMUM 8 words, concrete -- name the technique or the part

Score honestly: most pop songs are g<=2. Reserve g>=4 for songs where the guitar
part is genuinely worth a practice session. A song can fit his taste (high f) and
still be a poor guitar lesson (low g).

Reply with ONLY a JSON array, one object per song, same order as the input, each
{"n":<index>,"g":..,"f":..,"e":"..","d":..,"w":".."}. No prose, no markdown fence."""


def norm(s):
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s.lower())
    s = re.split(r" - (remaster|live|mono|stereo|single|radio|version)", s)[0]
    return re.sub(r"[^a-z0-9]+", "", s)


def curated_titles():
    """Songs already on a hand-curated board never need tagging."""
    out = set()
    for b in (read_json(DATA) or {}).get("boards", []):
        for song in b.get("songs", []):
            for p in song.get("parts", []):
                out.add(norm(p["t"]))
    return out


def prefiltered(tracks):
    """Split into (send to model, dropped for free). All the free wins live here."""
    have, seen = curated_titles(), set()
    send, dropped = [], []
    for t in tracks:
        key = norm(t["artist"].split(",")[0]) + "|" + norm(t["title"])
        gj = " ".join(t.get("genres", []))
        if key in seen or norm(t["title"]) in have:
            dropped.append(t)                       # duplicate, or already curated
        elif gj and DROP.search(gj) and not KEEP.search(gj):
            dropped.append(t)                       # genre says definitely not guitar
        else:
            seen.add(key)
            send.append(t)
    return send, dropped


def call(batch, key, retries=3):
    lines = [f'{i}. {t["artist"]} - {t["title"]}'
             + (f'  [{", ".join(t["genres"][:4])}]' if t.get("genres") else "")
             for i, t in enumerate(batch)]
    body = {
        "model": MODEL,
        "max_tokens": 60 * len(batch) + 200,
        "system": [{"type": "text", "text": RUBRIC,
                    "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": "\n".join(lines)}],
    }
    for attempt in range(retries):
        r = requests.post("https://api.anthropic.com/v1/messages", json=body, timeout=180,
                          headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                   "content-type": "application/json"})
        if r.status_code in (429, 500, 502, 503, 529):
            wait = int(r.headers.get("retry-after", 2 ** (attempt + 1)))
            print(f"    {r.status_code}, retrying in {wait}s")
            time.sleep(wait)
            continue
        if r.status_code != 200:
            raise SystemExit(f"API error {r.status_code}: {r.text[:300]}")
        d = r.json()
        text = "".join(b.get("text", "") for b in d.get("content", []))
        m = re.search(r"\[.*\]", text, re.S)
        if not m:
            print("    unparseable reply, retrying")
            continue
        try:
            return json.loads(m.group(0)), d.get("usage", {})
        except json.JSONDecodeError:
            print("    bad JSON, retrying")
    return None, {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=40)
    ap.add_argument("--limit", type=int, default=0, help="only tag N songs (for a test run)")
    ap.add_argument("--dry-run", action="store_true", help="show the cost estimate, call nothing")
    a = ap.parse_args()

    lib = read_json(LIBRARY)
    if not lib:
        raise SystemExit(f"No {LIBRARY.name} -- run tools/1_pull.py first.")
    tracks = lib["tracks"]
    cache = read_json(TAGS, {}) or {}

    send, dropped = prefiltered(tracks)
    todo = [t for t in send if t["id"] not in cache]
    if a.limit:
        todo = todo[:a.limit]

    print(f"{len(tracks)} liked · {len(dropped)} dropped free (dupes, already "
          f"curated, genre) · {len(send) - len(todo)} cached · {len(todo)} to tag")

    if a.dry_run or not todo:
        est = (len(todo) * 22 * PRICE_IN) + (len(todo) * 28 * PRICE_OUT)
        print(f"Estimated cost: ${est:.2f}")
        return

    key = need("ANTHROPIC_API_KEY", "Create one at https://console.anthropic.com/settings/keys")
    usage = {"in": 0, "out": 0, "cw": 0, "cr": 0}

    for i in range(0, len(todo), a.batch):
        batch = todo[i:i + a.batch]
        print(f"  tagging {i + 1}-{i + len(batch)} of {len(todo)}...")
        rows, u = call(batch, key)
        if rows is None:
            print("    batch failed, skipping (re-run to retry it)")
            continue
        for row in rows:
            n = row.get("n")
            if not isinstance(n, int) or not 0 <= n < len(batch):
                continue
            cache[batch[n]["id"]] = {k: row.get(k) for k in ("g", "f", "e", "d", "w")}
        usage["in"] += u.get("input_tokens", 0)
        usage["out"] += u.get("output_tokens", 0)
        usage["cw"] += u.get("cache_creation_input_tokens", 0)
        usage["cr"] += u.get("cache_read_input_tokens", 0)
        write_json(TAGS, cache)          # checkpoint after every batch

    cost = (usage["in"] * PRICE_IN + usage["out"] * PRICE_OUT
            + usage["cw"] * PRICE_CACHE_W + usage["cr"] * PRICE_CACHE_R)
    print(f"\nTagged {len(cache)} songs total.")
    print(f"Tokens: {usage['in']} in · {usage['out']} out · "
          f"{usage['cr']} cache-read · {usage['cw']} cache-write")
    print(f"Cost this run: ${cost:.3f}")
    print("Next: python3 tools/3_build.py")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tools"))
    main()
