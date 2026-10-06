"""Everything the app shows, loaded once at import from data/ (written by publish.py).

Loaded at import rather than per session: the files are small and identical for
every visitor, so the first page view should not pay for reading them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
QUANTILES = [f"q{q:.3f}" for q in (0.01, 0.025, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45,
                                   0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95,
                                   0.975, 0.99)]

# Plain names first: the audience is a health department, not a methods section.
MODEL_NAMES = {
    "gnn_st": "Neighborhood graph model",
    "lstm": "LSTM (sequence model)",
    "colagnn": "Cola-GNN (graph model from the literature)",
    "persistence": "Same as last week",
}
MODEL_SHORT = {"gnn_st": "Graph model", "lstm": "LSTM", "colagnn": "Cola-GNN",
               "persistence": "Same as last week"}
# Colour follows the model, never its rank: categorical slots 1-3, and the
# reference in neutral ink so it never reads as a competitor.
MODEL_CLASS = {"gnn_st": "s1", "lstm": "s2", "colagnn": "s3", "persistence": "sref"}
PRIMARY = "gnn_st"

CITY_INFO = {
    "boston": dict(
        label="Boston", area_word="neighborhood", areas_word="neighborhoods",
        unit="emergency-department visits for flu-like illness per 100,000 residents",
        unit_short="visits per 100k", fmt="{:.1f}", min_change=2.0,
        source="Boston Public Health Commission, public influenza dashboard (weekly ED "
               "visits for influenza-like illness by neighborhood)"),
    "chicago": dict(
        label="Chicago", area_word="ZIP code", areas_word="ZIP codes",
        unit="flu-like illness activity level, 1 (minimal) to 10 (very high)",
        unit_short="activity level", fmt="{:.1f}", cap=10,
        # CDC's ILI activity-level bands (minimal 1-3, low 4-5, moderate 6-7,
        # high 8-10), shifted onto the four names this app uses everywhere.
        fixed_levels=(4, 6, 8), min_change=1.0,
        source="Chicago Department of Public Health, “Influenza Risk Level by ZIP "
               "Code” on the City of Chicago Data Portal (Illinois ESSENCE ED data)",
        # Required by the City of Chicago Data Portal terms of use.
        disclaimer="This site provides applications using data that has been modified for "
                   "use from its original source, www.cityofchicago.org, the official website "
                   "of the City of Chicago. The City of Chicago makes no claims as to the "
                   "content, accuracy, timeliness, or completeness of any of the data provided "
                   "at this site. The data provided at this site is subject to change at any "
                   "time. It is understood that the data provided at this site is being used "
                   "at one's own risk."),
}

LEVELS = ("Low", "Moderate", "High", "Very high")
LEVEL_STATUS = {"Low": "good", "Moderate": "warning", "High": "serious", "Very high": "critical"}


@dataclass
class CityData:
    key: str
    info: dict
    meta: dict
    forecast: pd.DataFrame
    history: pd.DataFrame
    comparison: pd.DataFrame
    bt_scores: pd.DataFrame
    live_scores: pd.DataFrame | None
    trust_notes: list[str]
    geo: dict
    edges: list[tuple[str, str]]
    thresholds: pd.DataFrame = field(default_factory=pd.DataFrame)

    # --- basics ------------------------------------------------------------
    @property
    def label(self) -> str:
        return self.info["label"]

    @property
    def areas(self) -> list[str]:
        return list(self.history.columns)

    @property
    def origin(self) -> pd.Timestamp:
        return pd.Timestamp(self.meta["origin"])

    @property
    def horizons(self) -> list[int]:
        return sorted(int(h) for h in self.forecast["horizon"].unique())

    @property
    def models(self) -> list[str]:
        order = list(MODEL_NAMES)
        found = list(self.forecast["model"].unique())
        return sorted(found, key=lambda m: order.index(m) if m in order else 99)

    @property
    def preview(self) -> bool:
        return bool(self.meta.get("quick"))

    def fmt(self, value) -> str:
        if value is None or not np.isfinite(value):
            return "—"
        return self.info["fmt"].format(value)

    # --- observed ------------------------------------------------------------
    def latest(self) -> pd.Series:
        """Each area's value in the origin week, or its last reported week if BPHC
        suppressed that one."""
        hist = self.history.loc[:self.origin]
        return hist.ffill().iloc[-1]

    def citywide(self) -> pd.Series:
        return self.history.mean(axis=1, skipna=True)

    # --- forecast ------------------------------------------------------------
    def rows(self, model: str, area: str | None = None) -> pd.DataFrame:
        f = self.forecast[self.forecast["model"] == model]
        if area is not None:
            f = f[f["area"] == area]
        return f.sort_values("horizon")

    def at(self, model: str, horizon: int) -> pd.Series:
        """Median forecast per area at one horizon (horizon 0 = the latest observation)."""
        if horizon == 0:
            return self.latest()
        f = self.forecast[(self.forecast["model"] == model) & (self.forecast["horizon"] == horizon)]
        return f.set_index("area")["predicted"].reindex(self.areas)

    def citywide_forecast(self, model: str) -> pd.DataFrame:
        """Average over areas of each forecast column, per horizon. The band of an
        average is narrower than the average of bands; this is the readable
        approximation, and the page says it is an average of area forecasts."""
        f = self.forecast[self.forecast["model"] == model]
        cols = ["predicted", "lower", "upper", "q0.250", "q0.750"]
        out = f.groupby(["horizon", "target_date"])[cols].mean().reset_index()
        return out.sort_values("horizon")

    def trust(self, model: str, horizon: int) -> str:
        f = self.forecast[(self.forecast["model"] == model) & (self.forecast["horizon"] == horizon)]
        return str(f["trust"].iloc[0]) if len(f) and "trust" in f else "not backtested"

    # --- context ---------------------------------------------------------------
    def level(self, area: str, value: float) -> str | None:
        """Where a value sits against this area's own flu-season history."""
        if value is None or not np.isfinite(value):
            return None
        if "fixed_levels" in self.info:
            cuts = self.info["fixed_levels"]
            return LEVELS[sum(value >= c for c in cuts)]
        if area not in self.thresholds.index:
            return None
        t = self.thresholds.loc[area]
        if value < t["p50"]:
            return "Low"
        if value < t["p80"]:
            return "Moderate"
        if value < t["p95"]:
            return "High"
        return "Very high"

    def seasons(self, series: pd.Series | None = None) -> dict[str, pd.Series]:
        """A weekly series (default: the citywide average) by week of season, per
        season. Seasons open on 1 August."""
        city = (self.citywide() if series is None else series).dropna()
        out: dict[str, pd.Series] = {}
        for week, value in city.items():
            year = week.year if week.month >= 8 else week.year - 1
            start = pd.Timestamp(year=year, month=8, day=1)
            label = f"{year}-{str(year + 1)[2:]}"
            out.setdefault(label, {})[(week - start).days // 7] = value
        return {k: pd.Series(v).sort_index() for k, v in out.items()}

    def season_label(self, week: pd.Timestamp) -> str:
        year = week.year if week.month >= 8 else week.year - 1
        return f"{year}-{str(year + 1)[2:]}"

    def season_roles(self) -> dict[str, str]:
        """Each season's part in the archived model: "training" if the graph model fit
        on any of its weeks, "validation" if they were only held out (to choose when
        to stop training and how wide to draw the ranges), "current" for this one.
        Empty when the archive predates meta["training"]."""
        window = self.meta.get("training")
        if not window:
            return {}
        t0, t1 = (pd.Timestamp(d) for d in window["train_targets"])
        current = self.season_label(self.origin)
        roles = {}
        for label, s in self.seasons().items():
            year = int(label[:4])
            weeks = pd.Timestamp(year=year, month=8, day=1) + pd.to_timedelta(s.index * 7, unit="D")
            fit = ((weeks >= t0) & (weeks <= t1)).any()
            roles[label] = "current" if label == current else "training" if fit else "validation"
        return roles

    def typical_peak(self) -> float:
        """Median of past complete seasons' citywide peaks, skipping 2020-21, the
        season flu did not circulate."""
        current = self.season_label(self.origin)
        peaks = [s.max() for label, s in self.seasons().items()
                 if label not in (current, "2020-21") and len(s) >= 40]
        return float(np.median(peaks)) if peaks else float("nan")


def _thresholds(history: pd.DataFrame) -> pd.DataFrame:
    """Per-area percentiles of flu-season weeks (Oct-Mar) since July 2022."""
    recent = history.loc[history.index >= "2022-07-01"]
    season = recent[recent.index.month.isin([10, 11, 12, 1, 2, 3])]
    return pd.DataFrame({f"p{p}": season.quantile(p / 100) for p in (50, 80, 95)})


def _load(key: str) -> CityData | None:
    folder = DATA_DIR / key
    if not (folder / "meta.json").exists():
        return None
    meta = json.loads((folder / "meta.json").read_text())
    forecast = pd.read_csv(folder / "forecast.csv", parse_dates=["origin_date", "target_date"],
                           dtype={"area": str})
    history = pd.read_csv(folder / "history.csv", index_col="week", parse_dates=True)
    history.columns = [str(c) for c in history.columns]
    live = folder / "live_scores.csv"
    live_scores = (pd.read_csv(live, parse_dates=["origin_date", "target_date"], dtype={"area": str})
                   if live.exists() else None)
    trust_notes = [line[2:].strip() for line in (folder / "trust.md").read_text().splitlines()
                   if line.startswith("- ")]
    edges = pd.read_csv(folder / "edges.csv", dtype=str)
    city = CityData(
        key=key, info=CITY_INFO[key], meta=meta, forecast=forecast, history=history,
        comparison=pd.read_csv(folder / "backtest_comparison.csv"),
        bt_scores=pd.read_csv(folder / "backtest_scores.csv"), live_scores=live_scores,
        trust_notes=trust_notes, geo=json.loads((folder / "geo.json").read_text()),
        edges=list(zip(edges["a"], edges["b"])))
    city.thresholds = _thresholds(history)
    return city


CITIES: dict[str, CityData] = {k: c for k in CITY_INFO if (c := _load(k)) is not None}
BOSTON = CITIES.get("boston")
CHICAGO = CITIES.get("chicago")


def flusight(city: CityData, model: str | None = None) -> pd.DataFrame:
    """FluSight hub layout: one row per quantile."""
    f = city.forecast if model is None else city.forecast[city.forecast["model"] == model]
    cols = [c for c in QUANTILES if c in f.columns]
    long = f.melt(id_vars=["model", "origin_date", "target_date", "horizon", "area"],
                  value_vars=cols, var_name="q", value_name="value")
    return pd.DataFrame({
        "model": long["model"], "reference_date": long["origin_date"].dt.date,
        "target": "wk inc flu rate" if city.key == "boston" else "wk ili activity level",
        "horizon": long["horizon"], "target_end_date": long["target_date"].dt.date,
        "location": long["area"], "output_type": "quantile",
        "output_type_id": long["q"].str[1:].astype(float), "value": long["value"].round(3),
    }).sort_values(["model", "location", "horizon", "output_type_id"])
