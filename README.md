# Guitar Comeback HQ

Ed's guitar comeback plan as a small static web app: song boards with tab links and progress chips, the weekly practice rhythm, and the 12-week arc. Data lives in `data.json`; the page renders it. Designed to be edited by Claude Code on an always-on Mac and served by GitHub Pages.

## One-time setup on the Mac Mini

```bash
# 0. Prereqs: git, and (recommended) the GitHub CLI:  brew install gh && gh auth login

# 1. Put this folder somewhere permanent, then:
cd guitar-comeback
git init -b main
git add -A
git commit -m "Initial import from Cowork"

# 2. Create the GitHub repo and push (public repo — free GitHub Pages requires it*)
gh repo create guitar-comeback --public --source=. --push

# 3. Enable GitHub Pages from the main branch root
gh api -X POST "repos/{owner}/guitar-comeback/pages" \
  -f "source[branch]=main" -f "source[path]=/"
# (or on github.com: Settings → Pages → Deploy from a branch → main / (root))

# 4. Your URL (live a minute or two later):
#    https://<your-username>.github.io/guitar-comeback/
```

\* Pages on a **private** repo needs GitHub Pro. If you'd rather keep it private for free, Cloudflare Pages serves private repos on a free plan — same static files, no changes needed.

## Android home-screen shortcut

Open the Pages URL in Chrome → **⋮ menu → Add to Home screen → Install**. Thanks to the manifest + service worker it installs as a standalone app, launches full-screen, and works offline (song data refreshes whenever you're online).

## Day-to-day: editing via Claude Code

```bash
npm install -g @anthropic-ai/claude-code   # once; sign in with your Claude account
cd guitar-comeback
claude
```

Then just talk to it — `CLAUDE.md` teaches it the conventions:

> "Mark These Days as nailed, make Hang Me the week's focus, and rewrite This Week for a slide-heavy week. Commit and push."

The phone shortcut shows the update on next launch.

## Local preview

```bash
python3 -m http.server 8000   # then http://localhost:8000
```

(Needed because the page fetches `data.json` — opening index.html straight from Finder won't load the boards.)

## Files

| File | Purpose |
|---|---|
| `index.html` | Page, styling, render logic. Static prose sections live here. |
| `data.json` | **The state**: song boards, chips, this-week block, meta. |
| `sw.js` | Offline cache (bump `CACHE_VERSION` when assets change). |
| `manifest.webmanifest`, `icons/` | PWA install on Android. |
| `CLAUDE.md` | Conventions for Claude Code — read by every session. |
