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
| What's driving it | Why the graph model forecasts what it does: a waterfall from a usual week at this time of year to the forecast (this week's reading, recent and earlier weeks, weather, the calendar, neighbors), a map of how much each other neighborhood spills over, every neighborhood side by side, and the drivers week by week this season |
| All neighborhoods | All 14 at once, sorted by how fast each is forecast to rise |
| Track record | Would these forecasts have worked in past seasons, and are the 95% ranges honest? Plus the live 2026-27 scorecard |
| Chicago | The same pipeline on Chicago's ZIP-level data, and both cities against their own typical peak |
| Forecast table | (Analyst view) every number, filterable |
| How it works | The neighborhood network, how long each model takes to run, data sources, caveats, and CSV / FluSight downloads |

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

The app only reads `data/`. Each week, in `areaFluForecast`, the live forecast
loads the models trained once at the season start (nothing is retrained), then
explains the graph model's forecast (only the new week is computed; earlier
weeks are reused):

```bash
python scripts/live_forecast.py run --city boston --models-dir live/models/2026_27/boston
python scripts/live_forecast.py explain --city boston --models-dir live/models/2026_27/boston
```

then, here:

```bash
python publish.py          # copies the newest archived forecast per city into data/
```

`explain` writes `drivers.csv` beside the archived forecast, and `publish.py`
copies it for the What's driving it tab. The tab is left out when a forecast
has no `drivers.csv` (one made by retraining, whose weights were not saved).

`live_forecast.py` times every model as it runs and saves `runtime.csv` in each
archived forecast; `publish.py` gathers them into `data/<city>/runtimes.csv` for
the How it works tab.

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
