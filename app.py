"""Boston Flu Outlook: neighborhood flu forecasts, 1-4 weeks ahead, for BPHC.

    shiny run --reload app.py

Reads only the precomputed files in data/ (publish.py writes them from the live
forecast archive), so the app needs no model code and starts in about a second.
One audience selector decides which tabs exist and how much of the scoring is
shown; everything else is shared.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from shiny import App, reactive, render, ui

from core import charts as C
from core import data as D
from core import vocab as V

# Resolved from this file, not the working directory: the deploy target does
# not necessarily launch the app from its own folder.
APP_DIR = Path(__file__).parent
B, CHI = D.BOSTON, D.CHICAGO

# Same theme persistence as the NCAA app: restore the stored choice before first
# paint, re-apply after the dark-mode component upgrades, then save changes.
THEME_SCRIPT = """
(function () {
  var KEY = "flu-outlook-theme";
  var root = document.documentElement;
  var read = function () {
    try { return window.localStorage.getItem(KEY); } catch (e) { return null; }
  };
  var stored = read();
  var initial = (stored === "dark" || stored === "light") ? stored : "light";
  root.setAttribute("data-bs-theme", initial);
  window.addEventListener("load", function () {
    if (root.getAttribute("data-bs-theme") !== initial) {
      root.setAttribute("data-bs-theme", initial);
    }
    new MutationObserver(function () {
      var mode = root.getAttribute("data-bs-theme");
      if (mode !== "dark" && mode !== "light") return;
      try { window.localStorage.setItem(KEY, mode); } catch (e) {}
    }).observe(root, { attributes: true, attributeFilter: ["data-bs-theme"] });
  });
})();
"""

SHORT_AREA = {"Back Bay/Beacon Hill/Downtown/North End/West End": "Back Bay & Downtown",
              "Allston/Brighton": "Allston-Brighton"}


def short(city: D.CityData, area: str) -> str:
    return SHORT_AREA.get(area, area) if city.key == "boston" else f"ZIP {area}"


def date(d) -> str:
    return pd.Timestamp(d).strftime("%b %-d")


def map_bins(city: D.CityData) -> list[float]:
    recent = city.history.iloc[-104:].to_numpy().ravel().tolist()
    return C.bins_for(recent + city.forecast["predicted"].tolist(), city.info.get("cap"))


BINS = {k: map_bins(c) for k, c in D.CITIES.items()}


# --- small pieces -----------------------------------------------------------------

def tile(label: str, value, sub: str | None = None):
    return ui.div(ui.div(label, class_="tile-label"), ui.div(value, class_="tile-value"),
                  ui.div(sub or "", class_="tile-sub"), class_="tile")


def level_pill(level: str | None):
    if not level:
        return ui.span("not reported", class_="pill pill-sm pill-none")
    return ui.span(level, class_=f"pill pill-sm pill-{D.LEVEL_STATUS[level]}")


def trust_badge(verdict: str):
    text, status, icon = V.VERDICT.get(verdict, (verdict, "warning", "?"))
    return ui.span(f"{icon} {text}", class_=f"trust trust-{status}")


def legend(models: list[str], bands: bool = True, observed: bool = True):
    keys = []
    if observed:
        keys.append(ui.span(ui.span(class_="sw obs"), "Reported", class_="key"))
    for i, m in enumerate(models):
        cls = D.MODEL_CLASS.get(m, "s1")
        keys.append(ui.span(ui.span(class_=f"sw {cls}"), D.MODEL_SHORT.get(m, m), class_="key"))
        if i == 0 and bands:
            keys.append(ui.span(ui.span(class_=f"sw-band {cls} b50"), "likely range (50%)", class_="key"))
            keys.append(ui.span(ui.span(class_=f"sw-band {cls} b95"), "plausible range (95%)", class_="key"))
    return ui.div(*keys, class_="legend")


def direction(change: float) -> tuple[str, str]:
    if not np.isfinite(change):
        return "—", "hold"
    if change > 0.15:
        return "↑", "rise"
    if change < -0.15:
        return "↓", "fall"
    return "→", "hold steady"


def preview_banner(city: D.CityData):
    if not city.preview:
        return None
    return ui.div(ui.tags.b("Preview numbers."),
                  f"These {city.label} forecasts come from a quick test run (tiny models, "
                  f"data through {date(city.origin)}), not the production run. They show "
                  "how the page works; don't quote them.", class_="banner")


# --- blocks shared by Boston and Chicago -----------------------------------------------

def map_block(city: D.CityData, h: int, selected: str | None, input_id: str):
    values = city.at(D.PRIMARY, h)
    latest = city.latest()
    rows = city.rows(D.PRIMARY)
    tips = {}
    for area in city.areas:
        v = values.get(area, np.nan)
        lines = [short(city, area)]
        if h == 0:
            lines.append(f"Reported {date(city.origin)}: {city.fmt(v)}")
        else:
            r = rows[(rows["area"] == area) & (rows["horizon"] == h)]
            if len(r):
                r = r.iloc[0]
                lines.append(f"Forecast for {date(r['target_date'])}: {city.fmt(r['predicted'])}")
                lines.append(f"95% range {city.fmt(r['lower'])}–{city.fmt(r['upper'])}")
                lines.append(f"Now: {city.fmt(latest.get(area))}")
        lvl = city.level(area, v)
        if lvl:
            lines.append(f"Level: {lvl}")
        lines.append("Click for details")
        tips[area] = "\n".join(lines)
    target = city.origin + pd.Timedelta(weeks=h)
    when = (f"<strong>Week of {date(target)}</strong> · reported" if h == 0 else
            f"<strong>Week of {date(target)}</strong> · forecast, {h} week{'s' if h > 1 else ''} ahead")
    svg = C.choropleth(city.geo, values.to_dict(), BINS[city.key], tips=tips, selected=selected,
                       input_id=input_id)
    return ui.div(ui.div(ui.HTML(when), class_="when"), ui.HTML(svg),
                  ui.HTML(C.legend_bins(BINS[city.key], city.fmt, city.info["unit_short"])))


def ranked_block(city: D.CityData, h: int, input_id: str, limit: int | None = None):
    values = city.at(D.PRIMARY, h)
    latest = city.latest()
    order = values.sort_values(ascending=False, na_position="last")
    top = max(order.max(), 1e-9)
    items = []
    for area, v in list(order.items())[:limit]:
        width = 0 if not np.isfinite(v) else max(2, 100 * v / top)
        change = (v / latest[area] - 1) if h and np.isfinite(v) and latest.get(area, 0) > 0 else np.nan
        chg = "" if not np.isfinite(change) else f"{change * 100:+.0f}%"
        items.append(ui.tags.li(
            ui.span(short(city, area), class_="nm"),
            ui.div(ui.div(class_="bar", style=f"width:{width:.0f}%"), class_="bar-track"),
            ui.span(city.fmt(v), class_="val"),
            ui.span(chg or level_pill(city.level(area, v)), class_="chg"),
            **{"data-area": area, "data-input": input_id, "tabindex": "0",
               "data-tip": f"{short(city, area)}\n{city.fmt(v)} {city.info['unit_short']}"
                           + (f"\n{chg} vs now" if chg else "")}))
    more = (ui.p(f"Top {limit} of {len(order)} shown; the map has them all.", class_="note")
            if limit and len(order) > limit else None)
    return ui.div(ui.tags.ul(*items, class_="ranked"), more)


def fan_block(city: D.CityData, area: str | None, models: list[str], title: str, blurb: str):
    hist = city.citywide() if area is None else city.history[area]
    if area is None:
        forecasts = {m: city.citywide_forecast(m) for m in models}
    else:
        forecasts = {m: city.rows(m, area) for m in models}
    svg = C.fan_chart(hist, forecasts, unit=city.info["unit_short"], fmt=city.fmt,
                      cap=city.info.get("cap"))
    return ui.div(ui.h3(title), ui.p(blurb, class_="blurb"), legend(models), ui.HTML(svg),
                  class_="chart-card")


RIBBON_SETS = {"all": "All seasons", "train": "Training seasons only"}


def season_span(labels: list[str]) -> str:
    labels = sorted(labels)
    return labels[0] if len(labels) == 1 else f"{labels[0]} to {labels[-1]}"


def ribbons_block(city: D.CityData, area: str | None, which: str = "all"):
    """The season-ribbon chart, its blurb and legend. The card and the
    all/training toggle live outside this, so the toggle keeps its state."""
    series = city.citywide() if area is None else city.history[area]
    seasons = city.seasons(series)
    current = city.season_label(city.origin)
    roles = city.season_roles()
    past = sorted(k for k in seasons if k != current)
    held = [k for k in past if roles.get(k) == "validation"]
    if which == "train" and roles:
        past = [k for k in past if roles.get(k) == "training"]
        seasons = {k: v for k, v in seasons.items() if k in past or k == current}
    start = pd.Timestamp(year=int(current[:4]), month=8, day=1)
    f = city.citywide_forecast(D.PRIMARY) if area is None else city.rows(D.PRIMARY, area)
    pts = [((pd.Timestamp(r.target_date) - start).days // 7, r.predicted) for r in f.itertuples()]
    svg = C.ribbons(seasons, current, pts, unit=city.info["unit_short"], fmt=city.fmt)
    where = "the city" if area is None else short(city, area)
    if which == "train" and roles:
        against = (f"only the seasons the model learned from ({season_span(past)})"
                   + (f". {', '.join(held)} was held back to decide when to stop training and "
                      "how wide to draw the forecast ranges, so it is left out here" if held else ""))
        key = "training seasons"
    else:
        against = f"every season since {past[0]}" if past else "past seasons"
        key = "past seasons"
    return ui.div(
        ui.p(f"{where} this season (blue, with the forecast as dots) against {against}. "
             "Past seasons are grey; hover one to name it. The x-axis counts weeks from 1 August.",
             class_="blurb"),
        ui.div(ui.span(ui.span(class_="sw s1"), f"{current}", class_="key"),
               ui.span(ui.span(class_="sw past"), key, class_="key"), class_="legend"),
        ui.HTML(svg))


def city_tiles(city: D.CityData):
    cw = city.citywide()
    now = cw.loc[:city.origin].dropna().iloc[-1]
    hmax = max(city.horizons)
    fc = city.citywide_forecast(D.PRIMARY).set_index("horizon")
    ahead = fc.loc[hmax]
    change = ahead["predicted"] / now - 1 if now > 0 else np.nan
    arrow, _ = direction(change)
    h_rise = 2 if 2 in city.horizons else hmax
    mid = city.at(D.PRIMARY, h_rise)
    latest = city.latest()
    # Up 10% and by a real amount: on Chicago's 1-10 scale a 1.0 -> 1.2 forecast
    # is noise, not a rise.
    floor = city.info.get("min_change", 0)
    rising = int(((mid > latest * 1.10) & (mid - latest >= floor) & (latest > 0)).sum())
    peak = city.typical_peak()
    words = city.info["areas_word"]
    return ui.div(
        tile("Citywide now", city.fmt(now),
             f"average of {len(city.areas)} {words}, week of {date(city.origin)}"),
        tile(f"In {hmax} weeks", f"{arrow} {city.fmt(ahead['predicted'])}",
             f"{change * 100:+.0f}% · 95% range {city.fmt(ahead['lower'])}–{city.fmt(ahead['upper'])}"
             if np.isfinite(change) else ""),
        tile(f"{words.capitalize()} rising", f"{rising} of {len(city.areas)}",
             f"forecast up more than 10% in {h_rise} weeks"
             + (f" (and by {city.fmt(floor)}+)" if floor else "")),
        tile("Against a typical peak", f"{100 * now / peak:.0f}%" if np.isfinite(peak) else "—",
             f"of a typical season's peak ({city.fmt(peak)})"),
        class_="tiles")


def headline(city: D.CityData) -> str:
    cw = city.citywide()
    now = cw.loc[:city.origin].dropna().iloc[-1]
    hmax = max(city.horizons)
    ahead = city.citywide_forecast(D.PRIMARY).set_index("horizon").loc[hmax]
    _, verb = direction(ahead["predicted"] / now - 1 if now > 0 else np.nan)
    share = now / city.typical_peak()
    return (f"Flu-like illness in {city.label} is at <strong>{share:.0%} of a typical season's "
            f"peak</strong> and is expected to <strong>{verb}</strong> over the next {hmax} weeks.")


# --- UI -------------------------------------------------------------------------------

def topbar():
    chips = [ui.span(ui.HTML(f"BPHC data through <strong>{date(B.origin)}</strong>"), class_="chip"),
             ui.span(ui.HTML(f"Forecast issued <strong>{date(B.meta.get('issued', B.origin))}</strong>"),
                     class_="chip"),
             ui.span(f"{len(B.meta.get('archived_origins', [1]))} weekly forecast(s) on record",
                     class_="chip")]
    return ui.div(
        ui.div(ui.h1(ui.span(class_="brand-mark"), "Boston Flu Outlook", class_="brand"),
               ui.p("Neighborhood flu forecasts for the next four weeks, built on how "
                    "illness spreads between neighboring areas.", class_="brand-sub"),
               ui.div(*chips, class_="fresh"), class_="brand-block"),
        ui.div(ui.input_select("audience", "I am viewing as", V.MODES, selected="briefing"),
               ui.div(ui.tags.label("Theme", class_="theme-label"),
                      ui.input_dark_mode(id="theme", mode="light"), class_="theme-block"),
               class_="audience-block"),
        class_="topbar")


app_ui = ui.page_fluid(
    ui.head_content(
        ui.tags.title("Boston Flu Outlook"),
        ui.tags.meta(name="viewport", content="width=device-width, initial-scale=1"),
        ui.include_css(APP_DIR / "www" / "styles.css"),
        ui.tags.script(THEME_SCRIPT),
        ui.include_js(APP_DIR / "www" / "app.js"),
    ),
    topbar(),
    ui.output_ui("tabs"),
    ui.div(
        ui.span(f"Forecast origin {B.meta['origin']}", class_="version-chip"),
        "Experimental research forecasts from the GNN-Influenza-Boston project at "
        "Northeastern University, built on the Boston Public Health Commission's public "
        "dashboard data. Not an official BPHC product, and not medical advice. Forecasts "
        "are archived unchanged every week and scored against what actually happened.",
        class_="disclaimer"),
)


# --- server ----------------------------------------------------------------------------

def server(input, output, session):
    sel_area = reactive.value(B.areas[0] if B else None)
    sel_zip = reactive.value(None)

    mode = reactive.calc(lambda: input.audience() or "briefing")

    # --- tab shell, rebuilt when the audience changes -------------------------
    @render.ui
    def tabs():
        m = mode()
        with reactive.isolate():
            area = sel_area()
            ribbon_set = input.ribbon_set() if "ribbon_set" in input else "all"
        hmax_b = max(B.horizons)
        panels = {
            "outlook": ui.nav_panel(
                V.TAB_TITLES["outlook"],
                preview_banner(B),
                ui.p(ui.HTML(headline(B)), class_="callout"),
                city_tiles(B),
                ui.div(
                    ui.div(
                        ui.h3("Where flu-like illness is heading"),
                        ui.p("Drag the slider or press play to step the map from this week "
                             "through each forecast week. Click a neighborhood for its detail.",
                             class_="blurb"),
                        ui.input_slider("h", "Weeks ahead", 0, hmax_b, 0, step=1, ticks=True,
                                        animate=ui.AnimationOptions(interval=1400, loop=False)),
                        ui.output_ui("boston_map"), class_="card"),
                    ui.div(ui.h3("Ranked"),
                           ui.p("Same numbers as the map, highest first.", class_="blurb"),
                           ui.output_ui("boston_ranked"), class_="card"),
                    class_="grid-2"),
                ui.output_ui("boston_citywide"),
                value="outlook"),
            "detail": ui.nav_panel(
                V.TAB_TITLES["detail"],
                preview_banner(B),
                ui.div(
                    ui.input_select("area", "Neighborhood",
                                    {a: short(B, a) for a in B.areas}, selected=area),
                    ui.input_checkbox_group(
                        "models", "Models", {m: D.MODEL_SHORT[m] for m in B.models},
                        selected=[D.PRIMARY] + (["persistence"] if m == "analyst" else []),
                        inline=True),
                    class_="controls"),
                ui.output_ui("detail_body"),
                ui.div(
                    ui.h3("Is this season early, or big?"),
                    ui.input_radio_buttons("ribbon_set", None, RIBBON_SETS, selected=ribbon_set,
                                           inline=True)
                    if B.season_roles() else None,
                    ui.output_ui("detail_ribbons"),
                    class_="chart-card"),
                value="detail"),
            "all": ui.nav_panel(
                V.TAB_TITLES["all"],
                preview_banner(B),
                ui.h2("Every neighborhood at once"),
                ui.p("The graph model's selling point is that neighboring areas move "
                     "together, so it helps to see them side by side. Each card shows the "
                     "last 12 reported weeks (black) and the next four (blue, with the "
                     "plausible range). Click a card for its detail.", class_="blurb"),
                ui.div(ui.input_select("sort", "Sort by",
                                       {"rise": "Fastest rising", "now": "Highest now",
                                        "name": "A–Z"}, selected="rise"),
                       ui.input_switch("shared", "Same scale for every card", True),
                       class_="controls"),
                ui.output_ui("multiples"),
                value="all"),
            "record": ui.nav_panel(V.TAB_TITLES["record"], ui.output_ui("record"), value="record"),
            "chicago": ui.nav_panel(V.TAB_TITLES["chicago"], chicago_panel(), value="chicago"),
            "table": ui.nav_panel(
                V.TAB_TITLES["table"],
                ui.div(ui.input_select("tbl_city", "City", {k: c.label for k, c in D.CITIES.items()}),
                       ui.input_select("tbl_model", "Model", {m: D.MODEL_SHORT[m] for m in B.models}),
                       class_="controls"),
                ui.output_data_frame("table"),
                value="table"),
            "how": ui.nav_panel(V.TAB_TITLES["how"], how_panel(), value="how"),
        }
        wanted = [t for t in V.TABS[m] if t != "chicago" or CHI is not None]
        return ui.navset_card_tab(*[panels[t] for t in wanted], id="nav", selected=wanted[0])

    # --- map clicks: every clickable area lands on the detail view ---------------
    @reactive.effect
    @reactive.event(input.area_click)
    def _go_area():
        area = input.area_click()
        if area in B.areas:
            sel_area.set(area)
            ui.update_select("area", selected=area)
            ui.update_navs("nav", selected="detail")

    @reactive.effect
    @reactive.event(input.area)
    def _keep_area():
        sel_area.set(input.area())

    @reactive.effect
    @reactive.event(input.chi_click)
    def _go_zip():
        sel_zip.set(input.chi_click())
        ui.update_select("chi_area", selected=input.chi_click())

    # --- outlook ------------------------------------------------------------------
    @render.ui
    def boston_map():
        return map_block(B, int(input.h() or 0), None, "area_click")

    @render.ui
    def boston_ranked():
        return ranked_block(B, int(input.h() or 0), "area_click")

    @render.ui
    def boston_citywide():
        models = [D.PRIMARY] + (["persistence"] if mode() == "analyst" else [])
        return fan_block(B, None, models, "Citywide",
                         f"Average across the {len(B.areas)} neighborhoods, "
                         f"{B.info['unit']}. Hover for weekly values.")

    # --- detail -------------------------------------------------------------------
    @render.ui
    def detail_body():
        area = input.area() or sel_area()
        if area not in B.areas:
            area = B.areas[0]
        models = [m for m in (input.models() or [D.PRIMARY]) if m in B.models] or [D.PRIMARY]
        # Bands go to the graph model when it is shown, so they mean the same thing everywhere.
        models = sorted(models, key=lambda m: m != D.PRIMARY)
        rows = B.rows(models[0], area)
        now = B.latest()[area]
        first, last = rows.iloc[0], rows.iloc[-1]
        lvl_now = B.level(area, now)
        sentence = (
            f"In <strong>{short(B, area)}</strong>, {B.fmt(now)} {B.info['unit_short']} were "
            f"reported for the week of {date(B.origin)} ({(lvl_now or 'unrated').lower()} for "
            f"this neighborhood). The {D.MODEL_SHORT[models[0]].lower()} expects "
            f"<strong>{B.fmt(first['predicted'])}</strong> next week, and would be surprised "
            f"by anything outside {B.fmt(first['lower'])}–{B.fmt(first['upper'])}. "
            f"By {date(last['target_date'])}: {B.fmt(last['predicted'])} "
            f"({B.fmt(last['lower'])}–{B.fmt(last['upper'])}).")
        badges = ui.div(*[ui.span(ui.tags.b(D.MODEL_SHORT[m] + ": "),
                                  trust_badge(B.trust(m, 1)), " ")
                          for m in models if m != "persistence"],
                        class_="legend")
        return ui.div(
            ui.p(ui.HTML(sentence), class_="callout"),
            ui.div(ui.span("Past-season check, 1 week ahead:", class_="note"), badges),
            fan_block(B, area, models, f"{short(B, area)}: the next four weeks",
                      f"{B.info['unit'].capitalize()}. The vertical line is the latest "
                      "reported week; hover anywhere for that week's numbers."))

    @render.ui
    def detail_ribbons():
        area = input.area() or sel_area()
        if area not in B.areas:
            area = B.areas[0]
        return ribbons_block(B, area, input.ribbon_set() if "ribbon_set" in input else "all")

    # --- small multiples -----------------------------------------------------------
    @render.ui
    def multiples():
        latest = B.latest()
        hmax = max(B.horizons)
        ahead = B.at(D.PRIMARY, hmax)
        growth = (ahead / latest.replace(0, np.nan)) - 1
        order = {"rise": growth.sort_values(ascending=False).index,
                 "now": latest.sort_values(ascending=False).index,
                 "name": sorted(B.areas, key=lambda a: short(B, a))}[input.sort() or "rise"]
        shared_top = max(B.history.iloc[-12:].max().max(),
                         B.forecast.loc[B.forecast["model"] == D.PRIMARY, "upper"].max())
        cards = []
        for area in order:
            f = B.rows(D.PRIMARY, area)
            top = shared_top if input.shared() else max(B.history[area].iloc[-12:].max(), f["upper"].max())
            g = growth.get(area, np.nan)
            arrow, _ = direction(g)
            cards.append(ui.div(
                ui.div(ui.span(short(B, area), class_="mini-name"),
                       ui.span(f"{B.fmt(latest[area])} → {B.fmt(ahead[area])}", class_="mini-val"),
                       class_="mini-head"),
                ui.HTML(C.spark(B.history[area], f, ymax=top * 1.05)),
                ui.div(ui.span(level_pill(B.level(area, latest[area]))),
                       ui.span(f"{arrow} {g * 100:+.0f}% in {hmax} wk" if np.isfinite(g) else ""),
                       class_="mini-foot"),
                class_="mini", **{"data-area": area, "data-input": "area_click", "tabindex": "0",
                                  "data-tip": f"{short(B, area)}\nNow {B.fmt(latest[area])}, "
                                              f"in {hmax} weeks {B.fmt(ahead[area])}"}))
        return ui.div(*cards, class_="multiples")

    # --- track record ----------------------------------------------------------------
    @render.ui
    def record():
        return record_body(B, mode())

    # --- chicago ---------------------------------------------------------------------
    if CHI is not None:
        @render.ui
        def chi_map():
            return map_block(CHI, int(input.chi_h() or 0), sel_zip(), "chi_click")

        @render.ui
        def chi_ranked():
            return ranked_block(CHI, int(input.chi_h() or 0), "chi_click", limit=12)

        @render.ui
        def chi_zip():
            z = input.chi_area() or CHI.areas[0]
            return fan_block(CHI, z, [D.PRIMARY], f"{short(CHI, z)}: the next weeks",
                             "Activity level, 1 to 10. Values are capped at 10, so a very "
                             "high peak and a merely high one can look the same.")

    # --- forecast table + downloads ---------------------------------------------------
    @render.data_frame
    def table():
        city = D.CITIES[input.tbl_city() or "boston"]
        model = input.tbl_model() or D.PRIMARY
        f = city.rows(model)
        out = pd.DataFrame({
            city.info["area_word"]: [short(city, a) for a in f["area"]],
            "weeks ahead": f["horizon"], "week of": f["target_date"].dt.strftime("%Y-%m-%d"),
            "median": f["predicted"].round(2), "95% low": f["lower"].round(2),
            "95% high": f["upper"].round(2), "past-season check": f["trust"]})
        return render.DataGrid(out, height="520px", filters=True)

    @render.download(filename=lambda: f"boston_flu_forecast_{B.meta['origin']}.csv")
    def dl_csv():
        yield B.forecast.to_csv(index=False)

    @render.download(filename=lambda: f"boston_flu_forecast_{B.meta['origin']}_flusight.csv")
    def dl_flusight():
        yield D.flusight(B).to_csv(index=False)


# --- panels built once (static content) ---------------------------------------------------

def chicago_panel():
    if CHI is None:
        return ui.p("Chicago data is not published yet.", class_="empty")
    hmax = max(CHI.horizons)
    boston_share = B.citywide()
    chicago_share = CHI.citywide()
    series = {}
    for city, s in ((B, boston_share), (CHI, chicago_share)):
        current = city.season_label(city.origin)
        season = city.seasons(s).get(current, pd.Series(dtype=float))
        series[f"{city.label} {current}"] = 100 * season / city.typical_peak()
    return ui.div(
        preview_banner(CHI),
        ui.h2("Chicago: is the season arriving elsewhere?"),
        ui.p("The same forecasting pipeline, run on Chicago's ZIP-level data. Two reasons "
             "it's here: Chicago's data is often more current than Boston's, so it gives an "
             "early read on the season; and it shows the method working in a second city "
             "with no retuning.", class_="blurb"),
        ui.p(f"Chicago reports an activity level from 1 to 10 for each ZIP code, not a rate, "
             f"so its numbers can't be compared with Boston's directly. The chart below "
             f"puts both cities on one scale: each against its own typical peak.",
             class_="note"),
        city_tiles(CHI),
        ui.div(ui.h3("Each city against its own typical peak"),
               ui.p("100% is the median peak of past seasons in that city. Week 0 is 1 August.",
                    class_="blurb"),
               ui.div(*[ui.span(ui.span(class_=f"sw s{i + 1}"), name, class_="key")
                        for i, name in enumerate(series)], class_="legend"),
               ui.HTML(C.two_city(series)), class_="chart-card"),
        ui.div(
            ui.div(ui.h3("ZIP codes"),
                   ui.input_slider("chi_h", "Weeks ahead", 0, hmax, 0, step=1, ticks=True,
                                   animate=ui.AnimationOptions(interval=1400, loop=False)),
                   ui.output_ui("chi_map"), class_="card"),
            ui.div(ui.h3("Highest"), ui.output_ui("chi_ranked"), class_="card"),
            class_="grid-2"),
        fan_block(CHI, None, [D.PRIMARY], "Chicago citywide",
                  f"Average activity level across {len(CHI.areas)} ZIP codes."),
        ui.div(ui.input_select("chi_area", "ZIP code", {a: a for a in sorted(CHI.areas)}),
               class_="controls"),
        ui.output_ui("chi_zip"),
        ui.p(f"Source: {CHI.info['source']}.", class_="note"),
        ui.p(CHI.info["disclaimer"], class_="note"),
    )


def record_body(city: D.CityData, m: str):
    comp = city.comparison[city.comparison["model"].isin(city.models)]
    seasons = ", ".join(city.meta.get("backtest_seasons") or []) or "past seasons"
    header = [ui.tags.th("Weeks ahead")] + [ui.tags.th(D.MODEL_SHORT[mdl]) for mdl in city.models
                                            if mdl != "persistence"]
    body = []
    for h in city.horizons:
        cells = [ui.tags.td(f"{h}")]
        for mdl in city.models:
            if mdl == "persistence":
                continue
            r = comp[(comp["model"] == mdl) & (comp["horizon"] == h)]
            if not len(r):
                cells.append(ui.tags.td("—"))
                continue
            r = r.iloc[0]
            gain = (1 - r["relative_wis"]) * 100
            text = f"{abs(gain):.0f}% {'closer' if gain >= 0 else 'further off'}"
            extra = (ui.div(f"WIS {r['wis']:.2f} · relative {r['relative_wis']:.2f} · "
                            f"p(Holm) {r['p_holm']:.3f}", class_="note") if m == "analyst" else None)
            cells.append(ui.tags.td(ui.div(text), trust_badge(r["verdict"]), extra))
        body.append(ui.tags.tr(*cells))
    cover = (city.bt_scores[city.bt_scores["model"].isin(city.models)]
             .groupby(["model", "horizon"])["coverage95"].mean().reset_index())
    return ui.div(
        preview_banner(city),
        ui.h2("Would these forecasts have worked before?"),
        ui.p(f"Before trusting a forecast, we replay past seasons ({seasons}). Each model is "
             "trained only on data from before the season, then forecasts every week of it as "
             "if it were live. We compare it with the simplest possible rule: next week looks "
             "like this week.", class_="blurb"),
        ui.div(ui.h3("How much closer than “same as last week”?"),
               ui.p("The score counts both the miss and how honest the range was (a tight "
                    "range that misses is penalized more than a wide one). “20% closer” "
                    "means 20% less total error than the simple rule on the same weeks. The "
                    "badge says whether the gap is bigger than week-to-week luck.",
                    class_="blurb"),
               ui.div(ui.tags.table(ui.tags.thead(ui.tags.tr(*header)), ui.tags.tbody(*body),
                                    class_="score-table"), class_="table-scroll"),
               class_="chart-card"),
        ui.div(ui.h3("When it says “95% range”, is it right 95% of the time?"),
               ui.p("How often the real number landed inside each model's plausible range in "
                    "past seasons. Near 95% is honest; far below means overconfident.",
                    class_="blurb"),
               ui.HTML(C.coverage_dots(cover)), class_="chart-card"),
        live_block(city),
    )


def live_block(city: D.CityData):
    s = city.live_scores
    done = s[np.isfinite(s["wis"])] if s is not None else None
    title = ui.h3(f"This season, live ({city.season_label(city.origin)})")
    if done is None or done.empty:
        first = city.origin + pd.Timedelta(weeks=1)
        return ui.div(title, ui.p(
            f"Every weekly forecast is saved unchanged the day it is made. The first ones are "
            f"scored once BPHC reports the week of {date(first)}. This section then fills in "
            f"week by week: a prospective record nobody can tune after the fact.",
            class_="empty"), class_="chart-card")
    summary = done.groupby(["horizon", "model"]).agg(
        weeks=("origin_date", "nunique"), wis=("wis", "mean"), cover=("covered95", "mean")).reset_index()
    ref = summary[summary["model"] == "persistence"].set_index("horizon")["wis"]
    rows = []
    for r in summary[summary["model"] != "persistence"].itertuples():
        rel = r.wis / ref.get(r.horizon, np.nan)
        rows.append(ui.tags.tr(ui.tags.td(D.MODEL_SHORT.get(r.model, r.model)), ui.tags.td(r.horizon),
                               ui.tags.td(r.weeks),
                               ui.tags.td(f"{(1 - rel) * 100:+.0f}%" if np.isfinite(rel) else "—"),
                               ui.tags.td(f"{r.cover * 100:.0f}%")))
    return ui.div(title, ui.p("Archived forecasts that have now met the real numbers.",
                              class_="blurb"),
                  ui.div(ui.tags.table(ui.tags.thead(ui.tags.tr(
                      *[ui.tags.th(t) for t in ("Model", "Weeks ahead", "Weeks scored",
                                                "Closer than “same as last week”",
                                                "Inside 95% range")])),
                      ui.tags.tbody(*rows), class_="score-table"), class_="table-scroll"),
                  class_="chart-card")


def how_panel():
    shorts = {a: short(B, a) for a in B.areas}
    return ui.div(
        ui.h2("How the forecast works"),
        ui.div(
            ui.div(ui.h4("What it forecasts"), ui.p(
                f"Weekly {B.info['unit']}, for each of BPHC's {len(B.areas)} reporting "
                "neighborhoods, one to four weeks past the latest reported week. Each "
                "forecast is a range, not a single number.", class_="blurb"), class_="note-card"),
            ui.div(ui.h4("Why neighbors matter"), ui.p(
                "Flu moves between people who live, work and commute near each other. The "
                "model is a graph neural network: it reads each neighborhood's recent weeks "
                "together with its neighbors' (the lines on the map), plus weather and the "
                "time of year.", class_="blurb"), class_="note-card"),
            ui.div(ui.h4("How to read the ranges"), ui.p(
                "The darker band is where the number will likely land (half the time); the "
                "lighter band is the plausible range (95% of the time). Ranges widen further "
                "ahead because the future is less certain, and the track record tab checks "
                "that they really hold.", class_="blurb"), class_="note-card"),
            class_="note-grid"),
        ui.div(ui.h3("The neighborhood network"),
               ui.p("Each line joins two neighborhoods that share a border; larger dots have "
                    "more neighbors. Hover a line or a dot.", class_="blurb"),
               ui.HTML(C.network(B.geo, B.edges, shorts)), class_="chart-card"),
        ui.div(ui.h3("Data and caveats"),
               ui.tags.ul(
                   ui.tags.li(f"Boston: {B.info['source']}. Small counts are suppressed by BPHC "
                              "and appear as “not reported”."),
                   ui.tags.li("Weather: Open-Meteo.com historical archive (CC BY 4.0)."),
                   *([ui.tags.li(f"Chicago: {CHI.info['source']}. {CHI.info['disclaimer']}")]
                     if CHI else []),
                   ui.tags.li("Reporting delays and later revisions are not modeled: a forecast "
                              "uses the numbers as published on the day it is made."),
                   ui.tags.li("Levels (low to very high) compare a week with that "
                              "neighborhood's own flu-season weeks since July 2022: below the "
                              "median is low, top 5% is very high."),
                   ui.tags.li("The 2025-26 season was used to design the model, so its numbers "
                              "are not independent evidence; the published evaluation uses "
                              "earlier seasons, and 2026-27 is scored live.")),
               class_="card"),
        ui.div(ui.h3("Get the numbers"),
               ui.p("The current forecast for every neighborhood, model and week, with 23 "
                    "quantiles. The FluSight file follows the CDC forecast-hub layout.",
                    class_="blurb"),
               ui.div(ui.download_button("dl_csv", "Forecast (CSV)"),
                      ui.download_button("dl_flusight", "FluSight format (CSV)"),
                      class_="controls"),
               class_="card"),
    )


app = App(app_ui, server, static_assets=None)
