"""Plotly chart builders with one consistent visual system.

Rules applied everywhere (from the project's data-viz guidelines):
* one y-axis per chart (never dual axes);
* thin bars with rounded ends, 2px lines, recessive hairline grid;
* text in neutral ink, never in the series colour;
* a legend whenever there are 2+ series, none for a single series;
* rupee values formatted in Indian style (₹1.2L, ₹45K) on axes and hovers;
* every chart handles empty data by returning None (the page shows an empty state).

Palette: validated categorical slots (blue, orange) and a blue↔red diverging
pair — see README "Design".
"""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go

from src.money import format_inr, format_inr_compact

BLUE = "#2a78d6"
ORANGE = "#eb6834"
RED = "#e34948"
INK = "#0b0b0b"
INK_2 = "#52514e"
INK_3 = "#8a8983"
GRID = "#ebeae6"
SURFACE = "#fcfcfb"
FONT = "Inter, -apple-system, Segoe UI, Roboto, sans-serif"


def _nice_step(span: float, count: int = 5) -> float:
    if span <= 0:
        return 1.0
    raw = span / count
    magnitude = 10 ** math.floor(math.log10(raw))
    return next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)


def _rupee_axis(values_paise, min_value: float = 0) -> dict:
    """Axis in rupees with clean steps and Indian compact tick labels (₹45K, ₹1.2L)."""
    high = max([v for v in values_paise] + [0]) / 100
    low = min(min_value, 0) / 100
    step = _nice_step(high - low)
    first = math.floor(low / step) * step
    last = math.ceil(high / step) * step if high > 0 else 0
    ticks, value = [], first
    while value <= last + step * 1e-6:
        ticks.append(round(value, 2))
        value += step
    return dict(tickvals=ticks, ticktext=[format_inr_compact(t * 100, precision=2) for t in ticks],
                range=[first, last if last > first else first + step])


def _layout(fig: go.Figure, title: str, subtitle: str | None = None, height: int = 340,
            legend: bool = False) -> go.Figure:
    title_spec = dict(text=f"<b>{title}</b>", x=0.005, xanchor="left", xref="container", yref="container",
                      y=1, yanchor="top", pad=dict(t=8), font=dict(size=15, color=INK))
    if subtitle:
        title_spec["subtitle"] = dict(text=subtitle, font=dict(size=12, color=INK_2))
    fig.update_layout(
        title=title_spec,
        font=dict(family=FONT, size=12, color=INK_2),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=height,
        margin=dict(l=8, r=16, t=70 if subtitle else 52, b=8),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    font=dict(color=INK_2), bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="white", bordercolor=GRID, font=dict(family=FONT, color=INK, size=12)),
        bargap=0.35,
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID, tickfont=dict(color=INK_2), ticks="", zeroline=False)
    fig.update_yaxes(gridcolor=GRID, gridwidth=1, zeroline=False, tickfont=dict(color=INK_2), linecolor=GRID)
    return fig


def _bar_style(fig: go.Figure) -> None:
    fig.update_traces(marker_line_width=0, selector=dict(type="bar"))
    try:  # rounded data-ends (Plotly >= 5.19)
        fig.update_traces(marker_cornerradius=4, selector=dict(type="bar"))
    except ValueError:  # pragma: no cover - older Plotly
        pass


# ------------------------------------------------------------------ charts

def monthly_trend(monthly: pd.DataFrame) -> go.Figure | None:
    """Expenditure vs income by month — two series, same ₹ scale, one axis."""
    if monthly.empty or (monthly["expenditure_paise"].sum() == 0 and monthly["income_paise"].sum() == 0):
        return None
    x = monthly["month"].dt.strftime("%b %Y")
    fig = go.Figure()
    for column, name, color in (("expenditure_paise", "Expenditure", BLUE), ("income_paise", "Income", ORANGE)):
        values = monthly[column]
        fig.add_trace(go.Scatter(
            x=x, y=values / 100, name=name, mode="lines+markers",
            line=dict(color=color, width=2, shape="linear"),
            marker=dict(size=8, color=color, line=dict(color=SURFACE, width=2)),
            customdata=[format_inr(v) for v in values],
            hovertemplate=f"{name}: %{{customdata}}<extra></extra>",
        ))
    fig.update_layout(hovermode="x unified")
    fig.update_yaxes(**_rupee_axis(list(monthly["expenditure_paise"]) + list(monthly["income_paise"])))
    fig = _layout(fig, "Monthly expenditure and income", "Expenditure = spending debits, before refunds",
                  legend=True, height=380)
    fig.update_layout(margin=dict(t=96))
    return fig


def horizontal_bars(labels, values_paise, title: str, subtitle: str | None = None,
                    hover_extra: list[str] | None = None, color: str = BLUE, max_bars: int = 12) -> go.Figure | None:
    labels, values = list(labels)[:max_bars], [int(v) for v in list(values_paise)[:max_bars]]
    if not values or sum(values) == 0:
        return None
    extra = hover_extra[:max_bars] if hover_extra else [""] * len(values)
    fig = go.Figure(go.Bar(
        y=labels, x=[v / 100 for v in values], orientation="h", marker_color=color,
        text=[format_inr_compact(v) for v in values], textposition="outside",
        textfont=dict(color=INK_2, size=11), cliponaxis=False,
        customdata=list(zip([format_inr(v) for v in values], extra)),
        hovertemplate="<b>%{y}</b><br>%{customdata[0]}%{customdata[1]}<extra></extra>",
    ))
    _bar_style(fig)
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color=INK))
    axis = _rupee_axis(values)
    axis["range"] = [0, axis["range"][1] * 1.15]  # room for the value labels
    fig.update_xaxes(**axis, showgrid=True, gridcolor=GRID)
    height = max(220, 48 + 34 * len(values) + (24 if subtitle else 0))
    fig = _layout(fig, title, subtitle, height=height)
    fig.update_layout(bargap=0.38)
    return fig


def category_bars(categories: pd.DataFrame) -> go.Figure | None:
    if categories.empty:
        return None
    extra = [f"<br>{s:.1f}% of expenditure · {n} payments · avg {format_inr(a)}"
             for s, n, a in zip(categories["share_pct"], categories["transaction_count"],
                                categories["avg_transaction_paise"])]
    return horizontal_bars(categories["category"], categories["expenditure_paise"],
                           "Where the money went", "Expenditure by category", extra)


def merchant_bars(merchants: pd.DataFrame) -> go.Figure | None:
    if merchants.empty:
        return None
    extra = [f"<br>{c} · {n} payments" for c, n in zip(merchants["category"], merchants["transaction_count"])]
    return horizontal_bars(merchants["merchant"], merchants["expenditure_paise"],
                           "Top merchants", "By total expenditure", extra)


def weekday_columns(weekdays: pd.DataFrame) -> go.Figure | None:
    if weekdays.empty or weekdays["expenditure_paise"].sum() == 0:
        return None
    values = weekdays["expenditure_paise"]
    fig = go.Figure(go.Bar(
        x=weekdays["weekday_name"].str[:3], y=values / 100, marker_color=BLUE,
        customdata=list(zip(weekdays["weekday_name"], [format_inr(v) for v in values],
                            weekdays["transaction_count"],
                            [format_inr(v) if pd.notna(v) else "—" for v in weekdays["avg_transaction_paise"]])),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} · %{customdata[2]} payments"
                      "<br>avg %{customdata[3]}<extra></extra>",
    ))
    _bar_style(fig)
    fig.update_yaxes(**_rupee_axis(values))
    fig = _layout(fig, "Spending by weekday", "Total expenditure on each day of the week", height=300)
    fig.update_layout(bargap=0.45)
    return fig


def period_comparison(categories: pd.DataFrame, current_label: str, previous_label: str) -> go.Figure | None:
    """Grouped bars: previous vs current period by category (two series, one axis)."""
    if categories.empty or (categories["current_paise"].sum() == 0 and categories["previous_paise"].sum() == 0):
        return None
    data = categories.assign(total=categories["current_paise"] + categories["previous_paise"])
    data = data.sort_values("total", ascending=False).head(10)
    fig = go.Figure()
    for column, name, color in (("previous_paise", previous_label, ORANGE), ("current_paise", current_label, BLUE)):
        fig.add_trace(go.Bar(
            x=data["category"], y=data[column] / 100, name=name, marker_color=color,
            customdata=[format_inr(v) for v in data[column]],
            hovertemplate=f"<b>%{{x}}</b><br>{name}: %{{customdata}}<extra></extra>",
        ))
    _bar_style(fig)
    fig.update_xaxes(tickangle=-30)
    fig.update_yaxes(**_rupee_axis(list(data["current_paise"]) + list(data["previous_paise"])))
    fig = _layout(fig, "Category spending: this period vs previous", None, height=360, legend=True)
    fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08)
    return fig


def change_bars(frame: pd.DataFrame, label_column: str, title: str, top_n: int = 8) -> go.Figure | None:
    """Diverging bars for increases (red) / decreases (blue), zero baseline."""
    if frame.empty:
        return None
    data = frame[frame["change_paise"] != 0]
    if data.empty:
        return None
    data = data.reindex(data["change_paise"].abs().sort_values(ascending=False).index).head(top_n)
    data = data.sort_values("change_paise", ascending=False)
    values = [int(v) for v in data["change_paise"]]
    colors = [RED if v > 0 else BLUE for v in values]
    fig = go.Figure(go.Bar(
        y=data[label_column], x=[v / 100 for v in values], orientation="h", marker_color=colors,
        customdata=list(zip([("+" if v > 0 else "−") + format_inr(abs(v)) for v in values],
                            [format_inr(v) for v in data["previous_paise"]],
                            [format_inr(v) for v in data["current_paise"]])),
        hovertemplate="<b>%{y}</b><br>%{customdata[0]}<br>%{customdata[1]} → %{customdata[2]}<extra></extra>",
        text=[("+" if v > 0 else "−") + format_inr_compact(abs(v)) for v in values],
        textposition="outside", textfont=dict(color=INK_2, size=11), cliponaxis=False,
    ))
    _bar_style(fig)
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color=INK))
    low, high = min(values + [0]), max(values + [0])
    axis = _rupee_axis([high], min_value=low)
    pad = (axis["range"][1] - axis["range"][0]) * 0.25  # room for value labels
    axis["range"] = [axis["range"][0] - (pad if low < 0 else 0), axis["range"][1] + (pad if high > 0 else 0)]
    fig.update_xaxes(**axis, showgrid=True, gridcolor=GRID, zeroline=True, zerolinecolor=INK_3, zerolinewidth=1)
    height = max(220, 70 + 34 * len(values))
    return _layout(fig, title, "Red = spent more, blue = spent less", height=height)
