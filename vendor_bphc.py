"""Copy the site's renderer into the BPHC folder, for its offline-website script.

    python vendor_bphc.py                                   # ~/GNN-Influenza-Boston/BPHC/code/outlook
    python vendor_bphc.py --dest path/to/BPHC/code/outlook

BPHC/code/make_site.py turns one archived forecast into the whole site as a
single HTML file. It needs the app's layout and charts but not this repository,
so they travel as a copy, the way BPHC/code/live_forecast.py is a copy of the
package's script. Run this after changing app.py, core/, www/ or export_html.py.
The destination folder is generated: it is replaced on every run.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DEFAULT_DEST = Path.home() / "GNN-Influenza-Boston" / "BPHC" / "code" / "outlook"
FILES = ["app.py", "export_html.py", "core/__init__.py", "core/charts.py", "core/data.py",
         "core/stage.py", "core/vocab.py", "www/styles.css", "www/app.js"]
# Boston's boundaries and neighborhood network don't change week to week; publish.py
# builds them from the research repo's GeoJSON, which BPHC doesn't have.
STATIC = {"data/boston/geo.json": "boston/geo.json", "data/boston/edges.csv": "boston/edges.csv"}
NOTE = ("Generated copy of boston-flu-outlook/{name}. Edit it there and run "
        "vendor_bphc.py; changes made here are overwritten.")
COMMENT = {".py": "# {}\n", ".css": "/* {} */\n", ".js": "// {}\n"}

README = """# outlook/ (generated)

The Boston Flu Outlook site's layout, charts and offline exporter, copied from the
`boston-flu-outlook` repository by its `vendor_bphc.py`. `../make_site.py` uses them
to write the whole site as one HTML file; you don't run anything in here directly.

- `boston/geo.json`, `boston/edges.csv`: neighborhood boundaries (City of Boston
  official neighborhoods, grouped into BPHC's 14 areas) and which areas border each
  other. They don't change from week to week.
- Everything else is a copy: edit it upstream, not here.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    args = parser.parse_args()
    dest = args.dest
    if dest.exists():
        if not (dest / "README.md").read_text().startswith("# outlook/ (generated)"):
            raise SystemExit(f"{dest} exists and is not a generated outlook/ folder; not touching it.")
        shutil.rmtree(dest)
    for name in FILES:
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(COMMENT[target.suffix].format(NOTE.format(name=name))
                          + (APP_DIR / name).read_text())
    for src, rel in STATIC.items():
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(APP_DIR / src, dest / rel)
    (dest / "README.md").write_text(README)
    print(f"Outputs: {dest}")


if __name__ == "__main__":
    main()
