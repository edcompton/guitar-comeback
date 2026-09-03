# Where this project is at

**Resume with:** `cd ~/guitar-comeback && claude`, then *"read PROGRESS.md and continue"*.

`CLAUDE.md` holds the conventions (chip colours, editing rules, the Ed context). This
file holds **state and what's next** — the things that change. Last updated 2026-09-03.

---

## State of play

Live and healthy at **https://edcompton.github.io/guitar-comeback/** — repo
`edcompton/guitar-comeback`, public, GitHub Pages from `main` at root. Deploy is just
`git push`; Pages rebuilds in about a minute.

Verified working end to end: PWA installs from Chrome on Android, service worker
registers and caches offline (`gchq-v3`), 39 songs across 5 boards, every tab link
resolves, the ✓ → "Copy update for Claude" loop works.

Three things have been built, in order:

1. **The site** — imported from Cowork, git initialised, Pages enabled.
2. **The Spotify pipeline** (`tools/`) — 2,965 liked songs pulled, all 2,886 unique
   ones tagged by Haiku for guitar-learning value, top picks published as the
   "From your Spotify" board. Total spend $0.62.
3. **The mobile rework** — the page was built as a plan document but is used as a
   nightly tool. Restructured for the second job.

Mobile measurements before → after the rework, at 375px:

| | before | after |
|---|---|---|
| Page height | 19.4 screens | 8.9 screens |
| Tonight's instruction | 6.4 screens down | visible without scrolling |
| Song boards + ✓ buttons | 10.5 screens down | 3.3 screens down |
| Tick tap target | 22×22px (fails WCAG + HIG) | 44×44px |
| Dim text contrast | 3.07:1 (fails AA) | 4.68:1 |
| Update bar at 3 ticks | 236px, 29% of viewport | 56px fixed, 7% |

---

## Next up

### 0. The week block is stale — do this first

`thisWeek` still says *"Week 1 — the re-entry week"* while `meta.phase` says
*"II — Build"*. They contradict each other, `meta.updated` is 2026-08-25, and the
Tonight card's staleness warning is now firing on Ed's phone.

**This needs Ed, not Claude** — per `CLAUDE.md`, never invent progress. Ask what week
he's actually on and what's been nailed, then rewrite `thisWeek` and bump
`meta.updated` + `meta.phase`. Two-minute job, highest value on the list: the Tonight
card faithfully shows the *wrong* instruction every evening until it's done.

### 1. Tick writeback — the structural risk, needs a decision

Ticking a song on the phone writes to that device's `localStorage` and nothing else.
The canonical `data.json` only moves when Ed copies the update, gets to a laptop, and
pastes it to Claude. Realistically he ticks at 20:15 and never does the rest.

The mobile rework arguably made this *worse* — the nightly loop is faster now, so he'll
tick more and the record will drift further. If the boards still say "week 1" in two
months, the page stops reflecting reality and gets abandoned. This is the thing that
decides whether the project survives.

No option is free, and the choice is Ed's:

- **Serverless write path** — a small function (Vercel/Cloudflare) holding a GitHub
  token, which the page calls to commit a chip change. Real fix, one-tap from the
  phone. Costs: another deployed service, a secret to manage.
- **Private write path** — move the repo private, Cloudflare Pages for hosting, same
  function approach. More setup, less public surface.
- **Accept the manual loop, make it unmissable** — e.g. the Sunday review row already
  exists; make the update bar persistent and louder after a few ticks. Cheapest, but
  relies on habit, which is the thing that failed before.

A token cannot live in the page — the repo is public.

### 2. Keep the backlog fed

The backlog is deliberately short (12) and there are **410 qualifying candidates**, so
it refills easily. When a song gets nailed, promote it into a curated board in
`data.json`; `3_build.py` then stops suggesting it and the slot refills on the next
run. That keeps it a queue rather than a second library.

Refresh after a batch of new Spotify likes — monthly is plenty:

```bash
python3 tools/1_pull.py && python3 tools/2_tag.py
python3 tools/3_build.py --top 12 --min-guitar 4 --per-edge 3
```

Only new likes get tagged (cached by track id), so a refresh costs pennies.

### 3. Open question, low priority

All six reference sections collapse by default. That's clearly right for the 200th
visit; it may be wrong for the first visit in a low week, when rereading *"the player
who learned Kensington Blues is still in there"* is the point. If the page feels hollow,
open one or two by default — a one-line change.

---

## Gotchas worth not rediscovering

Established the hard way on this repo, not read off a changelog:

- **Spotify gives new apps no artist genres.** The field comes back empty — checked
  across 550 artists, every one. `GET /v1/artists?ids=` (bulk) also 403s for apps
  created after the Nov 2024 restrictions, while `GET /v1/artists/{id}` returns 200.
  Don't reinstate a genre crawl without checking the field is populated first: a
  1,600-artist sweep earned a `Retry-After: 85220` (~24h) throttle on that endpoint.
  Tagging on artist + title alone works fine for well-known music.
- **Prompt caching never engages** in `2_tag.py` — the rubric sits under Haiku's
  1024-token minimum, so every run reports `0 cache-read`. Costs about 4c across a full
  sweep. Not worth padding the prompt to fix.
- **Ultimate Guitar returns 404, not an empty page**, when a search has no results.
  Plenty of obscure blues sides genuinely have no tab, so `3_build.py` verifies each
  pick and substitutes the next candidate.
- **Spotify titles carry release cruft** ("- Live from Spotify SXSW 2014", "(feat. X)")
  that finds nothing on UG. `clean_title()` strips suffixes only — mid-title
  parentheticals are often part of the real name.
- **`cache.addAll()` is atomic** — one missing file fails the whole service worker
  install. `sw.js` caches per-asset for this reason.
- **`--limit` on `2_tag.py` takes the first N, which is a biased sample** — Spotify
  returns newest-first, so that's recent taste, not the library. Use `--sample`.
- **API credit top-ups take a few minutes to propagate.** A 400 "credit balance too
  low" right after paying is usually just delay; retry before debugging.

## Files not in the repo

These are gitignored and live only on the Mac mini. A fresh clone won't have them.

| File | What | Regenerate with |
|---|---|---|
| `.env` | `SPOTIFY_CLIENT_ID`, `ANTHROPIC_API_KEY` | by hand — see `tools/README.md` |
| `.spotify-token.json` | Refresh token, so auth only happens once | `1_pull.py` re-prompts |
| `library.json` | 2,965 liked songs (pulled 2026-08-27) | `1_pull.py` |
| `tags.json` | 2,886 cached tags — **the expensive one** | `2_tag.py`, ~$0.59 to rebuild |
| `artists.json` | Artist genre cache, all empty (see gotchas) | not worth rebuilding |
| `ug-cache.json` | Which UG searches returned tabs | `3_build.py` |

`library.json` and `tags.json` stay local deliberately: the repo is public and a full
liked-songs dump is more exposure than a practice backlog needs. Worth a manual backup
somewhere — `tags.json` is the only artefact that costs real money to recreate.
