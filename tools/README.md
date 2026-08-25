# Spotify → guitar backlog

Turns your Spotify liked songs into a board of Ultimate Guitar search links,
ranked for what's actually worth learning at your level.

Run it whenever you've liked a batch of new music — monthly is plenty.

## One-time setup

**1. A Spotify app** (for library access — the Spotify connector caps at 5 results
and can't enumerate your library).

- Go to https://developer.spotify.com/dashboard → **Create app**
- Name it anything. **Redirect URI must be exactly** `http://127.0.0.1:8888/callback`
  (Spotify allows the loopback IP but *not* `localhost`)
- Which API: tick **Web API**
- Save, then copy the **Client ID**. You do *not* need the client secret — auth
  uses PKCE, so no secret is ever stored on this machine.

**2. An Anthropic API key** for the tagging step — https://console.anthropic.com/settings/keys

**3. Put both in `.env`** in the repo root (gitignored, never committed):

```
SPOTIFY_CLIENT_ID=your_client_id_here
ANTHROPIC_API_KEY=sk-ant-your_key_here
```

## Running it

```bash
python3 tools/1_pull.py     # opens a browser once to authorise, then dumps library.json
python3 tools/2_tag.py      # tags with Haiku; prints exactly what it cost
python3 tools/3_build.py    # writes backlog.json, which the page renders
git add -A && git commit -m "Refresh Spotify backlog" && git push
```

Check the damage before spending anything:

```bash
python3 tools/2_tag.py --dry-run    # how many songs, estimated cost, no API calls
python3 tools/2_tag.py --limit 40   # tag only 40, to eyeball the quality first
```

## What it costs

Roughly **$0.30 per 2,000 songs**, and far less on later runs — tags are cached by
Spotify track id in `tags.json`, so a re-run only pays for music you've liked since.
The genre prefilter drops obvious non-guitar tracks before any API call, for free.

`2_tag.py` prints real token counts and the actual dollar cost at the end of every run.

## Tuning the picks

```bash
python3 tools/3_build.py --top 60          # longer board
python3 tools/3_build.py --min-guitar 4    # stricter: only strongly guitar-led songs
python3 tools/3_build.py --per-edge 20     # less balancing across growth edges
```

The rating rubric — what counts as a good song for *you* — is the `RUBRIC` string at
the top of `2_tag.py`. It encodes the player profile from `CLAUDE.md`: fingerstyle
strength, and pick/electric/slide as the growth edges. Edit it and delete `tags.json`
to re-tag from scratch.

## Files it creates

| File | Committed? | What |
|---|---|---|
| `library.json` | no — gitignored | Full liked-songs dump. Stays local; the repo is public. |
| `tags.json` | no — gitignored | Tag cache keyed by track id. Delete to force a re-tag. |
| `.spotify-token.json` | no — gitignored | Refresh token, so you only authorise once. |
| `backlog.json` | **yes** | The curated board the page renders. |
