#!/usr/bin/env python3
"""Pull every liked song (plus artist genres) from Spotify into library.json.

Auth is Authorization Code + PKCE, so only a Client ID is needed -- no client
secret ever touches this machine. The refresh token is cached in
.spotify-token.json (gitignored) so this only prompts once.

Usage:  python3 tools/1_pull.py
"""
import base64, hashlib, http.server, json, os, secrets, sys, threading, time
import urllib.parse, webbrowser
import requests
from common import ROOT, LIBRARY, need, read_json, write_json

REDIRECT = "http://127.0.0.1:8888/callback"   # Spotify allows loopback IP, not "localhost"
SCOPE = "user-library-read"
TOKEN_FILE = ROOT / ".spotify-token.json"
API = "https://api.spotify.com/v1"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _authorize(client_id):
    verifier = _b64(secrets.token_bytes(64))
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    state = _b64(secrets.token_bytes(16))
    url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "client_id": client_id, "response_type": "code", "redirect_uri": REDIRECT,
        "scope": SCOPE, "code_challenge_method": "S256", "code_challenge": challenge,
        "state": state,
    })

    got = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            ok = "code" in got and got.get("state") == state
            self.wfile.write(
                b"<body style='background:#131009;color:#e8c477;font:16px system-ui;"
                b"display:grid;place-items:center;height:100vh'><p>"
                + (b"Authorised. Close this tab and return to the terminal."
                   if ok else b"Something went wrong. Check the terminal.")
                + b"</p></body>")

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 8888), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    print("Opening Spotify authorisation in your browser...")
    print(f"  If it doesn't open, paste this in yourself:\n  {url}\n")
    webbrowser.open(url)

    deadline = time.time() + 300
    while "code" not in got and "error" not in got and time.time() < deadline:
        time.sleep(0.3)
    srv.shutdown()

    if got.get("error"):
        raise SystemExit(f"Spotify returned an error: {got['error']}")
    if "code" not in got:
        raise SystemExit("Timed out waiting for authorisation.")
    if got.get("state") != state:
        raise SystemExit("State mismatch -- aborting rather than trusting that redirect.")

    r = requests.post("https://accounts.spotify.com/api/token", data={
        "grant_type": "authorization_code", "code": got["code"],
        "redirect_uri": REDIRECT, "client_id": client_id, "code_verifier": verifier,
    }, timeout=30)
    r.raise_for_status()
    return r.json()


def _refresh(client_id, refresh_token):
    r = requests.post("https://accounts.spotify.com/api/token", data={
        "grant_type": "refresh_token", "refresh_token": refresh_token,
        "client_id": client_id,
    }, timeout=30)
    if r.status_code != 200:
        return None
    tok = r.json()
    tok.setdefault("refresh_token", refresh_token)
    return tok


def get_token():
    client_id = need("SPOTIFY_CLIENT_ID",
                     "Create an app at https://developer.spotify.com/dashboard, add "
                     f"redirect URI {REDIRECT}, then copy the Client ID.")
    cached = read_json(TOKEN_FILE)
    if cached and cached.get("refresh_token"):
        tok = _refresh(client_id, cached["refresh_token"])
        if tok:
            write_json(TOKEN_FILE, tok)
            return tok["access_token"]
        print("Cached token no longer valid -- re-authorising.")
    tok = _authorize(client_id)
    write_json(TOKEN_FILE, tok)
    return tok["access_token"]


def api_get(url, token, params=None):
    """GET with polite 429 handling."""
    for attempt in range(6):
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"},
                         params=params, timeout=30)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", "2")) + 1
            print(f"  rate limited, sleeping {wait}s")
            time.sleep(wait)
            continue
        if r.status_code in (502, 503, 504):
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    raise SystemExit(f"Gave up on {url}")


def main():
    token = get_token()

    print("Pulling liked songs...")
    tracks, url, params = [], f"{API}/me/tracks", {"limit": 50}
    while url:
        page = api_get(url, token, params)
        params = None                      # `next` already carries the query string
        for item in page.get("items", []):
            t = item.get("track") or {}
            if not t.get("id") or t.get("is_local"):
                continue
            tracks.append({
                "id": t["id"],
                "title": t["name"],
                "artist": ", ".join(a["name"] for a in t.get("artists", [])),
                "artist_ids": [a["id"] for a in t.get("artists", []) if a.get("id")],
                "album": (t.get("album") or {}).get("name", ""),
                "year": ((t.get("album") or {}).get("release_date") or "")[:4],
                "popularity": t.get("popularity", 0),
                "added": (item.get("added_at") or "")[:10],
            })
        url = page.get("next")
        print(f"  {len(tracks)} so far...", end="\r", flush=True)
    print(f"  {len(tracks)} liked songs.            ")

    # Artist genres: the one useful signal Spotify still gives away free.
    # (audio-features was deprecated for new apps in Nov 2024.)
    ids = sorted({i for t in tracks for i in t["artist_ids"]})
    print(f"Fetching genres for {len(ids)} artists...")
    genres = {}
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        for a in api_get(f"{API}/artists", token, {"ids": ",".join(chunk)}).get("artists", []):
            if a:
                genres[a["id"]] = a.get("genres", [])
        print(f"  {min(i+50, len(ids))}/{len(ids)}", end="\r", flush=True)
    print(" " * 30, end="\r")

    for t in tracks:
        g = []
        for aid in t["artist_ids"]:
            g.extend(genres.get(aid, []))
        t["genres"] = sorted(set(g))
        del t["artist_ids"]

    write_json(LIBRARY, {"pulled": time.strftime("%Y-%m-%d"), "tracks": tracks})
    n_g = sum(1 for t in tracks if t["genres"])
    print(f"\nWrote {LIBRARY.name}: {len(tracks)} tracks, {n_g} with genre data.")
    print("Next: python3 tools/2_tag.py")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tools"))
    main()
