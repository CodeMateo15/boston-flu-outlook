"""The weekly update in one command: new data -> forecast from saved models -> app.

    # 1. drop the new BPHC CSVs into ~/GNN-Influenza-Boston/Data/BPHC Flu Data/
    # 2. from this folder:
    .venv/bin/python weekly_update.py                    # Boston
    .venv/bin/python weekly_update.py --city chicago     # Chicago (posts Fridays)
    .venv/bin/python weekly_update.py --city boston chicago --commit --push

Per city it runs, in order:
    GNN-Influenza-Boston   refresh weather (Chicago: also download the CDPH data)
    areaFluForecast        export the data, `live_forecast.py run` with the models
                           frozen at the season start (the .pt files in
                           live/models/<season>/<city>; nothing is retrained),
                           `explain` (Boston), `score`
    this repo              publish.py --only <city>

A city whose newest week already has an archived forecast is skipped: archived
forecasts are never overwritten. Nothing is committed or pushed unless you pass
--commit / --push; a push redeploys the app on Connect Cloud. Everything printed is
also saved to logs/.

Every run (and `--status` alone, which runs nothing else) rewrites DATA_STATUS.md:
the newest week each source has, the newest forecast, and what the app shows.

If `run` stops with "The weekly rates before 2026-06-01 differ ... (a revised
export?)", the source revised weeks the models were trained on. They need
retraining once (`live_forecast.py train`, about 2.5 h for Boston), see
areaFluForecast's scripts/live_forecast.py.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).parent
HOME = Path.home()
RESEARCH = HOME / "GNN-Influenza-Boston"
AREAFLU = HOME / "Developer" / "areaFluForecast"
SEASON = "2026_27"
# areaFluForecast needs pandas and torch, which neither its .venv nor ours has
PY = os.environ.get("AREAFLU_PYTHON", "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12")
APP_PY = str(APP_DIR / ".venv" / "bin" / "python")

REFRESH = {
    "boston": [["Code/scrapers/scrape_weather.py", "--refresh"]],
    "chicago": [["Code/scrapers/build_chicago_panel.py", "--download"],
                ["Code/scrapers/scrape_weather_chicago.py", "--refresh"]],
}
EXPLAIN = {"boston"}  # Chicago's drivers haven't been computed yet
BPHC_CSV = RESEARCH / "Data" / "BPHC Flu Data" / "BPHC Dashboard Influenza Neighborhood.csv"
# newest weeks on the Chicago portal; week_start has been wrong there (2514-10-24), so
# go by week_end
CHICAGO_API = ("https://data.cityofchicago.org/resource/8vvr-jv2g.json?$select=week_end,"
               "min(:created_at)%20as%20posted&$group=week_end&$order=week_end%20DESC&$limit=1")

LOG = None


def say(text: str = "") -> None:
    print(text, flush=True)
    LOG.write(text + "\n")
    LOG.flush()


def sh(cmd: list[str], cwd: Path, env: dict | None = None) -> None:
    say(f"\n$ (cd {cwd}) {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, cwd=cwd, env={**os.environ, **(env or {})}, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in proc.stdout:
        # the per-epoch progress lines are noise in a weekly run
        if not line.startswith("Epoch "):
            say(line.rstrip())
    if proc.wait():
        say(f"\nFAILED (exit {proc.returncode}): {' '.join(cmd)}")
        sys.exit(proc.returncode)


def newest_week(city: str) -> pd.Timestamp:
    return pd.Timestamp(pd.read_csv(AREAFLU / "live" / city / "rates.csv", usecols=["week"])["week"].max())


def span(start: pd.Timestamp) -> str:
    end = start + pd.Timedelta(days=6)
    return f"{start:%b} {start.day} - {end:%b} {end.day}"


def source_week(city: str) -> tuple[pd.Timestamp | None, str]:
    """Start of the newest week the source has, and where that came from."""
    if city == "boston":
        rates = pd.read_csv(BPHC_CSV, usecols=["date_type", "date_value_start"])
        week = pd.Timestamp(rates.loc[rates["date_type"] == "Weekly", "date_value_start"].max())
        return week, f"BPHC CSVs in ~/{BPHC_CSV.parent.relative_to(HOME)}"
    # curl, not urllib: the python.org Python has no CA certificates installed
    try:
        row = json.loads(subprocess.run(["curl", "-sf", "--max-time", "30", CHICAGO_API],
                                        capture_output=True, text=True, check=True).stdout)[0]
    except (subprocess.CalledProcessError, ValueError, IndexError):  # offline: write the rest
        return None, "Chicago portal unreachable"
    posted = pd.Timestamp(row["posted"]).tz_convert("America/Chicago")
    return (pd.Timestamp(row["week_end"]) - pd.Timedelta(days=6),
            f"Chicago portal, posted {posted:%a %b} {posted.day} {posted:%H:%M} CT")


def write_status() -> None:
    lines = ["# Data status", "",
             f"Written by `weekly_update.py` on {time.strftime('%Y-%m-%d %H:%M')}. Check here "
             "before an update to see whether a city has a new week.", "",
             "| City | Newest week in the source | Newest forecast | In the app | New week to run? |",
             "|---|---|---|---|---|"]
    for city in ("boston", "chicago"):
        week, where = source_week(city)
        archived = sorted(p.name for p in (AREAFLU / "live" / SEASON / city).glob("20*-*-*"))
        newest = pd.Timestamp(archived[-1]) if archived else None
        meta = APP_DIR / "data" / city / "meta.json"
        shown = json.loads(meta.read_text())["origin"] if meta.exists() else "none"
        todo = ("unknown" if week is None or newest is None else
                f"yes: `weekly_update.py --city {city}`" if week > newest else "no")
        lines.append(f"| {city.capitalize()} | {span(week) if week is not None else '?'} ({where}) "
                     f"| {span(newest) if newest is not None else 'none'} | {shown} | {todo} |")
    lines += ["",
              "Weeks run Sunday to Saturday. Forecast folders, and `origin` in the app, are named "
              "by the start of the newest week they use: forecast 2026-10-18 uses data through "
              "Sat Oct 24 and forecasts the four weeks after it.", "",
              "- Boston: BPHC has no feed. Download the dashboard CSVs into "
              "`~/GNN-Influenza-Boston/Data/BPHC Flu Data/`; the week shown above is the newest "
              "one in those files, not what BPHC has posted.",
              "- Chicago: the City of Chicago portal (dataset 8vvr-jv2g) posts every Friday around "
              "12:30 pm CT, adding the week that ended the Saturday before. So on a Friday the new "
              "week is the one that ended six days earlier, one week behind Boston's.", ""]
    (APP_DIR / "DATA_STATUS.md").write_text("\n".join(lines))
    say(f"\nWrote {APP_DIR / 'DATA_STATUS.md'}")


def update(city: str) -> pd.Timestamp | None:
    """Forecast the newest week; the week, or None when it was forecast already."""
    say(f"\n=== {city} ===")
    for script in REFRESH[city]:
        sh([PY, *script], RESEARCH)
    env = {"AREAFLU_RESEARCH_REPO": str(RESEARCH), "PYTHONPATH": "src"}
    sh([PY, "scripts/export_sample.py", "--city", city, "--out", f"live/{city}"], AREAFLU, env)

    week = newest_week(city)
    archive = AREAFLU / "live" / SEASON / city / f"{week:%Y-%m-%d}"
    if archive.exists():
        say(f"\n{city}: the newest week ({week:%Y-%m-%d}) is already forecast in {archive}; "
            "no new data, skipping.")
        return None

    models = ["--models-dir", f"live/models/{SEASON}/{city}"]
    live = [PY, "scripts/live_forecast.py"]
    sh([*live, "run", "--city", city, *models], AREAFLU, env)
    if city in EXPLAIN:
        sh([*live, "explain", "--city", city, *models], AREAFLU, env)
    sh([*live, "score", "--city", city], AREAFLU, env)
    return week


def main() -> None:
    global LOG
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--city", nargs="+", choices=["boston", "chicago"], default=["boston"])
    parser.add_argument("--commit", action="store_true", help="commit data/ when something changed")
    parser.add_argument("--push", action="store_true", help="also push (redeploys the app)")
    parser.add_argument("--status", action="store_true",
                        help="only rewrite DATA_STATUS.md (what each source has)")
    args = parser.parse_args()

    (APP_DIR / "logs").mkdir(exist_ok=True)
    log_path = APP_DIR / "logs" / f"weekly_{time.strftime('%Y-%m-%d_%H%M%S')}.log"
    LOG = log_path.open("w")
    start = time.time()
    if args.status:
        write_status()
        return

    done = {city: week for city in args.city if (week := update(city)) is not None}
    if not done:
        write_status()
        say(f"\nNothing new to publish. Log: {log_path}")
        return
    sh([APP_PY, "publish.py", "--only", *done], APP_DIR)
    write_status()

    # "Boston data through Oct 24": the last day of the newest week
    message = "; ".join(f"{city.capitalize()} data through {(w + pd.Timedelta(days=6)):%b} "
                        f"{(w + pd.Timedelta(days=6)).day}" for city, w in done.items())
    say(f"\nDone in {(time.time() - start) / 60:.1f} min. Log: {log_path}")
    if args.commit or args.push:
        sh(["git", "add", "data", "DATA_STATUS.md"], APP_DIR)
        sh(["git", "commit", "-m", message], APP_DIR)
    if args.push:
        sh(["git", "push"], APP_DIR)
    if not args.push:
        say("\nCheck it locally:  .venv/bin/shiny run --launch-browser app.py")
        if not args.commit:
            say(f'Then:  git add data DATA_STATUS.md && git commit -m "{message}" && git push')
        else:
            say("Then:  git push")


if __name__ == "__main__":
    main()
