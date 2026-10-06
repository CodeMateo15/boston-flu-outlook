"""Wording per audience, and which tabs each one sees.

Briefing is for a health-department lead deciding what to say this week: plain
words, the graph model up front, no scoring jargon. Analyst keeps the same pages
and adds the numbers behind them (scores, p-values, the full forecast table).
"""

MODES = {"briefing": "Health department briefing", "analyst": "Analyst"}

TABS = {
    "briefing": ["outlook", "detail", "all", "record", "chicago", "how"],
    "analyst": ["outlook", "detail", "all", "record", "chicago", "table", "how"],
}

TAB_TITLES = {
    "outlook": "This week", "detail": "Neighborhood", "all": "All neighborhoods",
    "record": "Track record", "chicago": "Chicago", "table": "Forecast table",
    "how": "How it works",
}

# Plain-language verdicts from the backtest, keyed by the package's verdict text.
VERDICT = {
    "better than persistence": ("Beats “same as last week”", "good", "✓"),
    "not clearly better than persistence": ("Slightly better, not clearly", "warning", "~"),
    "no better than persistence": ("No better than “same as last week”", "critical", "✕"),
    "worse than persistence": ("Worse than “same as last week”", "critical", "✕"),
    "not enough data": ("Not enough data", "warning", "?"),
    "not backtested": ("Not checked yet", "warning", "?"),
    "reference": ("Reference", "warning", "•"),
}
