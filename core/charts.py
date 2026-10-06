"""Inline-SVG charts. Every colour is a CSS class (www/styles.css), so light and
dark mode are handled by the token blocks there, not here.

Hover: any element with `data-tip` gets the shared tooltip (www/app.js); the
first line is the heading. Line charts put one invisible full-height column per
week under the pointer, so the whole plot is the hit target, not the 2px line.
"""

from __future__ import annotations

import math
from html import escape

import numpy as np
import pandas as pd

from .data import MODEL_CLASS, MODEL_SHORT


def esc(text) -> str:
    return escape(str(text), quote=True)


def nice_ticks(hi: float, n: int = 4) -> list[float]:
    if not np.isfinite(hi) or hi <= 0:
        return [0.0, 1.0]
    raw = hi / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    return [i * step for i in range(int(math.ceil(hi / step)) + 1)]


def _fmt_tick(v: float) -> str:
    return f"{v:.0f}" if v == int(v) else f"{v:.1f}"


def _date(d) -> str:
    return pd.Timestamp(d).strftime("%b %-d")


class Frame:
    """Plot geometry: maps dates and values to pixels."""

    def __init__(self, width, height, x0, x1, ymax, left=44, right=16, top=14, bottom=28):
        self.w, self.h = width, height
        self.l, self.r, self.t, self.b = left, right, top, bottom
        self.x0, self.x1 = pd.Timestamp(x0), pd.Timestamp(x1)
        self.ticks = nice_ticks(ymax)
        self.ymax = self.ticks[-1]

    def x(self, d) -> float:
        span = (self.x1 - self.x0).days or 1
        return self.l + (pd.Timestamp(d) - self.x0).days / span * (self.w - self.l - self.r)

    def y(self, v) -> float:
        return self.t + (1 - v / self.ymax) * (self.h - self.t - self.b)

    def grid(self, unit_label: str = "") -> str:
        parts = []
        for v in self.ticks:
            y = self.y(v)
            parts.append(f'<line class="grid" x1="{self.l}" x2="{self.w - self.r}" y1="{y:.1f}" y2="{y:.1f}"/>'
                         f'<text class="tick" x="{self.l - 6}" y="{y + 4:.1f}" text-anchor="end">{_fmt_tick(v)}</text>')
        parts.append(f'<line class="axis" x1="{self.l}" x2="{self.w - self.r}" y1="{self.y(0):.1f}" y2="{self.y(0):.1f}"/>')
        # Month ticks along the bottom.
        month = pd.Timestamp(self.x0.year, self.x0.month, 1) + pd.offsets.MonthBegin(1)
        while month <= self.x1:
            x = self.x(month)
            parts.append(f'<text class="tick" x="{x:.1f}" y="{self.h - 8}" text-anchor="middle">{month.strftime("%b")}</text>')
            month += pd.offsets.MonthBegin(1)
        if unit_label:
            parts.append(f'<text class="tick" x="{self.l}" y="{self.t - 3}">{esc(unit_label)}</text>')
        return "".join(parts)


def _path(points) -> str:
    pts = [(x, y) for x, y in points if np.isfinite(y)]
    return "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) if pts else ""


def _band(fr: Frame, dates, lo, hi) -> str:
    top = [(fr.x(d), fr.y(v)) for d, v in zip(dates, hi)]
    bottom = [(fr.x(d), fr.y(v)) for d, v in zip(dates[::-1], lo[::-1])]
    return "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in top + bottom) + "Z"


# --- fan chart ---------------------------------------------------------------------

def fan_chart(history: pd.Series, forecasts: dict[str, pd.DataFrame], *, unit: str, fmt,
              weeks: int = 20, width: int = 760, height: int = 300, cap: float | None = None) -> str:
    """Observed weeks, then each model's median for 1-4 weeks ahead. The first model
    in `forecasts` gets the 50% and 95% bands; the others are lines only, so the
    bands never pile up."""
    origin = history.dropna().index.max()
    hist = history.loc[:origin].iloc[-weeks:]
    last = hist.dropna().iloc[-1]
    ends = [f["target_date"].max() for f in forecasts.values() if len(f)]
    x1 = max(ends) if ends else origin
    top = max([hist.max()] + [f["upper"].max() for f in forecasts.values() if len(f)])
    if cap:
        top = min(max(top, 1), cap)
    fr = Frame(width, height, hist.index.min(), x1, top * 1.05)
    out = [f'<svg class="chart fan" viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="Observed and forecast {esc(unit)}">', fr.grid(unit)]
    out.append(f'<line class="today" x1="{fr.x(origin):.1f}" x2="{fr.x(origin):.1f}" y1="{fr.t}" '
               f'y2="{fr.y(0):.1f}"/><text class="today-label" x="{fr.x(origin) + 4:.1f}" '
               f'y="{fr.t + 10}">latest data</text>')
    for i, (model, f) in enumerate(forecasts.items()):
        if not len(f):
            continue
        cls = MODEL_CLASS.get(model, "s1")
        dates = [origin] + list(f["target_date"])
        if i == 0:
            out.append(f'<path class="band95 {cls}" d="{_band(fr, dates, [last] + list(f["lower"]), [last] + list(f["upper"]))}"/>')
            out.append(f'<path class="band50 {cls}" d="{_band(fr, dates, [last] + list(f["q0.250"]), [last] + list(f["q0.750"]))}"/>')
        med = [(fr.x(d), fr.y(v)) for d, v in zip(dates, [last] + list(f["predicted"]))]
        out.append(f'<path class="line fc {cls}" d="{_path(med)}"/>')
        out += [f'<circle class="dot {cls}" cx="{x:.1f}" cy="{y:.1f}" r="4"/>' for x, y in med[1:]]
    obs = [(fr.x(d), fr.y(v)) for d, v in hist.items()]
    out.append(f'<path class="line obs" d="{_path(obs)}"/>')
    out.append(f'<circle class="dot obs" cx="{fr.x(origin):.1f}" cy="{fr.y(last):.1f}" r="4"/>')
    # Hover columns.
    weeks_all = list(hist.index) + sorted({d for f in forecasts.values() for d in f["target_date"]})
    step = (fr.x(weeks_all[1]) - fr.x(weeks_all[0])) if len(weeks_all) > 1 else 20
    for d in weeks_all:
        lines = [f"Week of {_date(d)}"]
        if d in hist.index and np.isfinite(hist.get(d, np.nan)):
            lines.append(f"Observed: {fmt(hist[d])}")
        elif d <= origin:
            lines.append("Observed: not reported")
        for model, f in forecasts.items():
            row = f[f["target_date"] == d]
            if len(row):
                r = row.iloc[0]
                lines.append(f"{MODEL_SHORT.get(model, model)}: {fmt(r['predicted'])} "
                             f"(95%: {fmt(r['lower'])}–{fmt(r['upper'])})")
        x = fr.x(d)
        out.append(f'<g class="col" data-tip="{esc(chr(10).join(lines))}">'
                   f'<rect class="hit" x="{x - step / 2:.1f}" y="{fr.t}" width="{step:.1f}" height="{fr.y(0) - fr.t:.1f}"/>'
                   f'<line class="guide" x1="{x:.1f}" x2="{x:.1f}" y1="{fr.t}" y2="{fr.y(0):.1f}"/></g>')
    out.append("</svg>")
    return "".join(out)


# --- season ribbons ------------------------------------------------------------------

def ribbons(seasons: dict[str, pd.Series], current: str, forecast: list[tuple[int, float]], *,
            unit: str, fmt, width: int = 760, height: int = 280) -> str:
    """This season against every past one, by week since 1 August. Past seasons are
    recessive grey; the current one carries the colour (emphasis, not identity)."""
    top = max(s.max() for s in seasons.values())
    if forecast:
        top = max(top, max(v for _, v in forecast))
    ticks = nice_ticks(top * 1.05)
    ymax = ticks[-1]
    l, r, t, b = 44, 16, 14, 28
    X = lambda wk: l + wk / 52 * (width - l - r)
    Y = lambda v: t + (1 - v / ymax) * (height - t - b)
    out = [f'<svg class="chart ribbons" viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="This season compared with past seasons">']
    for v in ticks:
        out.append(f'<line class="grid" x1="{l}" x2="{width - r}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>'
                   f'<text class="tick" x="{l - 6}" y="{Y(v) + 4:.1f}" text-anchor="end">{_fmt_tick(v)}</text>')
    for i, m in enumerate(["Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul"]):
        out.append(f'<text class="tick" x="{X(i * 52 / 12 + 2):.1f}" y="{height - 8}" text-anchor="middle">{m}</text>')
    out.append(f'<text class="tick" x="{l}" y="{t - 3}">{esc(unit)}</text>')
    for label, s in sorted(seasons.items()):
        if label == current:
            continue
        pts = [(X(wk), Y(v)) for wk, v in s.items()]
        peak = s.idxmax()
        out.append(f'<path class="past" d="{_path(pts)}" data-tip="{esc(label)}&#10;Peak {esc(fmt(s.max()))}, '
                   f'week {int(peak)} of the season"/>')
    if current in seasons:
        s = seasons[current]
        pts = [(X(wk), Y(v)) for wk, v in s.items()]
        out.append(f'<path class="line now" d="{_path(pts)}"/>')
        if forecast and len(s):
            fpts = [(X(s.index[-1]), Y(s.iloc[-1]))] + [(X(wk), Y(v)) for wk, v in forecast]
            out.append(f'<path class="line now-fc" d="{_path(fpts)}"/>')
            out += [f'<circle class="dot now" cx="{x:.1f}" cy="{y:.1f}" r="4"/>' for x, y in fpts[1:]]
        if len(s):
            x, y = X(s.index[-1]), Y(s.iloc[-1])
            out.append(f'<text class="direct" x="{x + 8:.1f}" y="{y - 8:.1f}">{esc(current)}</text>')
    out.append("</svg>")
    return "".join(out)


# --- map --------------------------------------------------------------------------------

def bins_for(values: list[float], cap: float | None = None) -> list[float]:
    """Five upper edges for six classes, on rounded numbers, fixed across horizons so
    the animation compares like with like."""
    if cap:
        return [2, 4, 6, 8, 9.5]
    v = np.array([x for x in values if np.isfinite(x)])
    hi = np.nanpercentile(v, 97) if len(v) else 1
    edges = nice_ticks(hi, 6)[1:6]
    while len(edges) < 5:
        edges.append(edges[-1] * 1.5)
    return edges


def choropleth(geo: dict, values: dict[str, float], edges: list[float], *, tips: dict[str, str],
               selected: str | None = None, input_id: str = "area_click",
               labels: dict[str, tuple[float, float, str]] | None = None) -> str:
    vb = geo["viewBox"]
    out = [f'<svg class="chart map" viewBox="{vb}" role="img" aria-label="Map">']
    if geo.get("context"):
        out.append(f'<path class="context" d="{geo["context"]}"/>')
    for area, shape in geo["areas"].items():
        v = values.get(area, np.nan)
        cls = "bna" if not np.isfinite(v) else f"b{sum(v > e for e in edges)}"
        sel = " selected" if area == selected else ""
        out.append(f'<path class="area {cls}{sel}" d="{shape["d"]}" fill-rule="evenodd" '
                   f'data-area="{esc(area)}" data-input="{input_id}" data-tip="{esc(tips.get(area, area))}" '
                   f'tabindex="0"/>')
    if selected and selected in geo["areas"]:
        out.append(f'<path class="area-outline" d="{geo["areas"][selected]["d"]}" fill-rule="evenodd"/>')
    for area, (x, y, text) in (labels or {}).items():
        out.append(f'<text class="map-label" x="{x:.1f}" y="{y:.1f}" text-anchor="middle">{esc(text)}</text>')
    out.append("</svg>")
    return "".join(out)


def legend_bins(edges: list[float], fmt, unit: str) -> str:
    cells = []
    bounds = [0.0] + list(edges)
    for i in range(6):
        text = f"{fmt(bounds[i])}–{fmt(bounds[i + 1])}" if i < 5 else f"over {fmt(edges[-1])}"
        cells.append(f'<span class="lg-cell"><span class="lg-swatch b{i}"></span>{esc(text)}</span>')
    cells.append('<span class="lg-cell"><span class="lg-swatch bna"></span>not reported</span>')
    return f'<div class="legend-bins"><span class="lg-title">{esc(unit)}</span>{"".join(cells)}</div>'


# --- small multiple -------------------------------------------------------------------

def spark(history: pd.Series, f: pd.DataFrame, *, ymax: float, width=220, height=92) -> str:
    origin = history.dropna().index.max()
    hist = history.loc[:origin].iloc[-12:]
    last = hist.dropna().iloc[-1]
    x1 = f["target_date"].max() if len(f) else origin
    fr = Frame(width, height, hist.index.min(), x1, ymax, left=4, right=4, top=6, bottom=6)
    out = [f'<svg class="chart spark" viewBox="0 0 {width} {height}" aria-hidden="true">',
           f'<line class="axis" x1="4" x2="{width - 4}" y1="{fr.y(0):.1f}" y2="{fr.y(0):.1f}"/>']
    if len(f):
        dates = [origin] + list(f["target_date"])
        out.append(f'<path class="band95 s1" d="{_band(fr, dates, [last] + list(f["lower"]), [last] + list(f["upper"]))}"/>')
        out.append(f'<path class="line fc s1" d="{_path([(fr.x(d), fr.y(v)) for d, v in zip(dates, [last] + list(f["predicted"]))])}"/>')
    out.append(f'<path class="line obs" d="{_path([(fr.x(d), fr.y(v)) for d, v in hist.items()])}"/>')
    out.append(f'<line class="today" x1="{fr.x(origin):.1f}" x2="{fr.x(origin):.1f}" y1="6" y2="{fr.y(0):.1f}"/>')
    out.append("</svg>")
    return "".join(out)


# --- network ------------------------------------------------------------------------------

def network(geo: dict, edges: list[tuple[str, str]], short: dict[str, str]) -> str:
    out = [f'<svg class="chart network" viewBox="{geo["viewBox"]}" role="img" '
           f'aria-label="Which areas the model treats as neighbours">']
    for area, shape in geo["areas"].items():
        out.append(f'<path class="net-area" d="{shape["d"]}" fill-rule="evenodd"/>')
    cents = {a: s["c"] for a, s in geo["areas"].items()}
    for a, b in edges:
        if a in cents and b in cents:
            (x1, y1), (x2, y2) = cents[a], cents[b]
            out.append(f'<line class="net-edge" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                       f'data-tip="{esc(short.get(a, a))} ↔ {esc(short.get(b, b))}&#10;share a border"/>')
    degree = {a: sum(a in e for e in edges) for a in cents}
    for a, (x, y) in cents.items():
        out.append(f'<circle class="net-node" cx="{x}" cy="{y}" r="{5 + degree[a]:.0f}" '
                   f'data-tip="{esc(short.get(a, a))}&#10;{degree[a]} neighbouring areas"/>')
    out.append("</svg>")
    return "".join(out)


# --- track record ---------------------------------------------------------------------------

def coverage_dots(table: pd.DataFrame, width=520, height=None) -> str:
    """How often the truth fell inside the 95% band, per model and horizon.
    Rows are model x horizon; the reference line marks 95%."""
    rows = table.sort_values(["model", "horizon"])
    height = height or 30 + 22 * len(rows)
    l, r = 200, 40
    X = lambda p: l + (p - 50) / 50 * (width - l - r)
    out = [f'<svg class="chart dots" viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="Coverage of the 95% range">']
    for p in (50, 75, 100):
        out.append(f'<line class="grid" x1="{X(p):.1f}" x2="{X(p):.1f}" y1="10" y2="{height - 18}"/>'
                   f'<text class="tick" x="{X(p):.1f}" y="{height - 4}" text-anchor="middle">{p}%</text>')
    out.append(f'<line class="target" x1="{X(95):.1f}" x2="{X(95):.1f}" y1="10" y2="{height - 18}"/>'
               f'<text class="tick" x="{X(95):.1f}" y="9" text-anchor="middle">target 95%</text>')
    for i, row in enumerate(rows.itertuples()):
        y = 24 + i * 22
        pct = 100 * row.coverage95
        out.append(f'<text class="row-label" x="{l - 10}" y="{y + 4}" text-anchor="end">'
                   f'{esc(MODEL_SHORT.get(row.model, row.model))}, {row.horizon} wk</text>')
        out.append(f'<g data-tip="{esc(MODEL_SHORT.get(row.model, row.model))}, {row.horizon} week(s) ahead&#10;'
                   f'Truth inside the 95% range {pct:.0f}% of the time">'
                   f'<rect class="hit" x="{l}" y="{y - 10}" width="{width - l - r}" height="20"/>'
                   f'<circle class="dot {MODEL_CLASS.get(row.model, "s1")}" cx="{X(max(50, pct)):.1f}" cy="{y}" r="5"/></g>')
    out.append("</svg>")
    return "".join(out)


def two_city(series: dict[str, pd.Series], *, width=760, height=260) -> str:
    """Each city as a share of its own typical peak, by week of season: one axis,
    two indexed series, so no dual scale is needed."""
    top = max(100, max(s.max() for s in series.values() if len(s)))
    ticks = nice_ticks(top * 1.05)
    ymax = ticks[-1]
    l, r, t, b = 44, 70, 14, 28
    X = lambda wk: l + wk / 52 * (width - l - r)
    Y = lambda v: t + (1 - v / ymax) * (height - t - b)
    out = [f'<svg class="chart twocity" viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="Each city against its own typical peak">']
    for v in ticks:
        out.append(f'<line class="grid" x1="{l}" x2="{width - r}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>'
                   f'<text class="tick" x="{l - 6}" y="{Y(v) + 4:.1f}" text-anchor="end">{v:.0f}%</text>')
    out.append(f'<line class="target" x1="{l}" x2="{width - r}" y1="{Y(100):.1f}" y2="{Y(100):.1f}"/>')
    for i, m in enumerate(["Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul"]):
        out.append(f'<text class="tick" x="{X(i * 52 / 12 + 2):.1f}" y="{height - 8}" text-anchor="middle">{m}</text>')
    for i, (name, s) in enumerate(series.items()):
        if not len(s):
            continue
        cls = f"s{i + 1}"
        pts = [(X(wk), Y(v)) for wk, v in s.items()]
        out.append(f'<path class="line {cls}" d="{_path(pts)}"/>')
        x, y = pts[-1]
        out.append(f'<circle class="dot {cls}" cx="{x:.1f}" cy="{y:.1f}" r="4" '
                   f'data-tip="{esc(name)}&#10;{s.iloc[-1]:.0f}% of a typical peak"/>')
        out.append(f'<text class="direct" x="{x + 8:.1f}" y="{y + 4:.1f}">{esc(name)}</text>')
    out.append("</svg>")
    return "".join(out)
