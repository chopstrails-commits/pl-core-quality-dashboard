# PL Core Quality Dashboard

Static site for [CQ_v1](../PL%20Predictive%20Model), the Premier League squad-quality
analytics project. Club core quality (10-season history + latest transition), a
filterable full-player database, and the current summer transfer window.

## What this is

A **static, single-page site** — `index.html` embeds its data directly (no backend,
no API calls, no build step on the host). It's a snapshot of `PL Predictive Model`'s
pipeline output at the time it was last built, not a live view of that project.

## Regenerating after a pipeline update

Whenever `PL Predictive Model`'s data changes (a re-scored season, a fresh transfer
pull, a new stat source):

```bash
python3 build_data.py   # pulls from ../PL Predictive Model/data/ -> data.json
python3 build_site.py   # injects data.json into template.html -> index.html
git add data.json index.html
git commit -m "Refresh dashboard data"
git push
```

`build_data.py` takes an optional path argument if the source project ever moves:
`python3 build_data.py /path/to/PL\ Predictive\ Model`.

## Files

- `template.html` — the page shell (markup, CSS, JS). Edit this for layout/behavior changes.
- `build_data.py` — pulls and reshapes data from the pipeline's CSVs into `data.json`.
- `build_site.py` — merges `data.json` into `template.html` to produce `index.html`.
- `data.json` / `index.html` — generated, committed (so Render has nothing to build).

## Deploy

- **GitHub:** `chopstrails-commits/pl-core-quality-dashboard` (private), branch `main`.
- **Render:** Static Site. Build Command: blank. Publish Directory: `.` (index.html is
  at repo root). Auto-deploys on push to `main`. No env vars needed.
