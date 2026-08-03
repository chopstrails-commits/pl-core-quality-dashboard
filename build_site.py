"""Inject data.json into template.html to produce index.html.

Run after build_data.py. Keeps the static site self-contained (no fetch, no
build step needed on Render) by embedding the data directly in the page.
"""
from pathlib import Path

ROOT = Path(__file__).parent
template = (ROOT / "template.html").read_text(encoding="utf-8")
data = (ROOT / "data.json").read_text(encoding="utf-8")
out = template.replace("__DASHBOARD_DATA__", data)
(ROOT / "index.html").write_text(out, encoding="utf-8")
print(f"Wrote {ROOT / 'index.html'} ({len(out):,} bytes)")
