# Boston Flu Outlook

Neighborhood flu forecasts for Boston, 1–4 weeks ahead, from the graph neural
network in the GNN-Influenza-Boston project, with Chicago alongside as a second city.
Built in Shiny for Python for the Boston Public Health Commission.

**Experimental research forecasts. Not an official BPHC product.**

## What's in it

| Tab | What it answers |
|---|---|
| This week | Where is flu-like illness heading? A map you can play forward week by week, a ranked list, and a citywide line with forecast ranges |
| Neighborhood | One neighborhood's next four weeks, with a model toggle, and this season against every season since 2017 or only the seasons the model trained on |
| All neighborhoods | All 14 at once, sorted by how fast each is forecast to rise |
| Track record | Would these forecasts have worked in past seasons, and are the 95% ranges honest? Plus the live 2026-27 scorecard |
| Chicago | The same pipeline on Chicago's ZIP-level data, and both cities against their own typical peak |
| Forecast table | (Analyst view) every number, filterable |
| How it works | The neighborhood network, data sources, caveats, and CSV / FluSight downloads |

The "I am viewing as" selector switches between a plain-language briefing and an
analyst view that adds the scores behind each verdict.

## Run locally

```bash
cd ~/Developer/boston-flu-outlook
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m venv --clear .venv   # first time only
.venv/bin/pip install -r requirements.txt     # first time only
.venv/bin/shiny run --reload --launch-browser app.py
```

It opens at http://127.0.0.1:8000. Run every command from this folder: the app
reads `data/` and `www/` next to `app.py`. If port 8000 is taken, add `--port 8050`.

Build `.venv` with a single Python and always use the `.venv/bin/...` commands. If
you have Anaconda too, a bare `python3.12` may resolve to Anaconda's copy, and
re-running `venv` with it over an existing `.venv` mixes the two interpreters (the
app then crashes on start in `ctypes`). `--clear` rebuilds from scratch, so the
first line is safe to re-run.

## Weekly update

The app only reads `data/`. Each week, after the live forecast has run
(`areaFluForecast/scripts/live_forecast.py`, on Explorer):

```bash
python publish.py          # copies the newest archived forecast per city into data/
```

then commit `data/` and push; Connect Cloud redeploys from the repo. A forecast made
with smoke-test settings carries `"quick": true` in its metadata, and the app shows
a "preview numbers" banner on every page.

## Deploying (Posit Connect Cloud)

Connect Cloud deploys straight from this GitHub repository. New content → Shiny →
pick the repo, branch `main`, primary file `app.py`. It reads `requirements.txt`
and `.python-version` (3.12).

## Data

- Boston: Boston Public Health Commission public influenza dashboard (weekly ED
  visits for influenza-like illness per 100,000, by neighborhood).
- Chicago: Chicago Department of Public Health, "Influenza Risk Level by ZIP Code",
  City of Chicago Data Portal.
- Boundaries: City of Boston official neighborhoods; City of Chicago ZIP code boundaries.
- Weather (a model input): Open-Meteo.com (CC BY 4.0).

The repository holds only these public numbers and our forecasts of them: no model
code, no weights.
