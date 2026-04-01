"""
Dynamic Load Balancer - Dashboard
===================================
Plotly Dash dashboard connected to the real Engine.

Run:
    pip install dash plotly pandas
    python app.py
Then open: http://127.0.0.1:8050
"""

import random
from collections import deque
from datetime import datetime

import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objs as go

from engine import Engine

# ─────────────────────────────────────────────
# ENGINE + HISTORY
# ─────────────────────────────────────────────

NUM_PROCESSORS = 4
ALGORITHMS = ["Round Robin", "Least Loaded", "Work Stealing"]

MAX_HISTORY = 60
engine = Engine(num_processors=NUM_PROCESSORS)
history = {
    "timestamps": deque(maxlen=MAX_HISTORY),
    "loads": [deque(maxlen=MAX_HISTORY) for _ in range(NUM_PROCESSORS)],
}

# ─────────────────────────────────────────────
# DASH APP
# ─────────────────────────────────────────────

app = dash.Dash(__name__, title="Load Balancer Dashboard")

PROCESSOR_COLORS = ["#4F86C6", "#5BAD8F", "#E07B54", "#9B72CF"]

app.layout = html.Div(
    style={"fontFamily": "'IBM Plex Mono', monospace", "background": "#0f1117", "minHeight": "100vh", "padding": "24px"},
    children=[

        # ── Header ───────────────────────────────
        html.Div(
            style={"marginBottom": "24px", "borderBottom": "1px solid #2a2d3a", "paddingBottom": "16px",
                   "display": "flex", "justifyContent": "space-between", "alignItems": "flex-end"},
            children=[
                html.Div([
                    html.H1("Load Balancer", style={"color": "#e8eaf0", "margin": 0, "fontSize": "22px",
                                                     "fontWeight": "500", "letterSpacing": "0.05em"}),
                    html.Span("Dynamic Multiprocessor Scheduler", style={"color": "#5a5f7a", "fontSize": "13px"}),
                ]),
                html.Div(id="live-clock", style={"color": "#5a5f7a", "fontSize": "13px"}),
            ]
        ),

        # ── Controls row ─────────────────────────
        html.Div(
            style={"display": "flex", "gap": "12px", "marginBottom": "24px", "flexWrap": "wrap", "alignItems": "center"},
            children=[
                html.Span("Algorithm:", style={"color": "#8b90a8", "fontSize": "13px"}),
                dcc.Dropdown(
                    id="algo-dropdown",
                    options=[{"label": a, "value": a} for a in ALGORITHMS],
                    value=ALGORITHMS[0],
                    clearable=False,
                    style={"width": "200px", "fontSize": "13px"},
                ),
                html.Button(
                    "Inject Task Burst",
                    id="inject-btn",
                    n_clicks=0,
                    style={"background": "#1e3a5f", "color": "#6eaff5", "border": "1px solid #2a5fa8",
                           "padding": "8px 16px", "borderRadius": "6px", "cursor": "pointer",
                           "fontSize": "13px", "fontFamily": "inherit"},
                ),
                html.Span(id="inject-feedback", style={"color": "#5BAD8F", "fontSize": "13px"}),
            ]
        ),

        # ── KPI cards ────────────────────────────
        html.Div(
            id="kpi-cards",
            style={"display": "grid", "gridTemplateColumns": "repeat(4, 1fr)", "gap": "12px", "marginBottom": "24px"},
        ),

        # ── CPU load line chart ───────────────────
        html.Div(
            style={"background": "#161920", "borderRadius": "10px", "padding": "16px",
                   "border": "1px solid #1e2130", "marginBottom": "16px"},
            children=[
                html.P("CPU Load Over Time (%)", style={"color": "#8b90a8", "fontSize": "12px",
                                                          "margin": "0 0 12px 0", "letterSpacing": "0.08em"}),
                dcc.Graph(id="load-chart", config={"displayModeBar": False}, style={"height": "220px"}),
            ]
        ),

        # ── Queue depth + per-processor bars ─────
        html.Div(
            style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px", "marginBottom": "16px"},
            children=[
                html.Div(
                    style={"background": "#161920", "borderRadius": "10px", "padding": "16px",
                           "border": "1px solid #1e2130"},
                    children=[
                        html.P("Task Queue Depth", style={"color": "#8b90a8", "fontSize": "12px",
                                                           "margin": "0 0 12px 0", "letterSpacing": "0.08em"}),
                        dcc.Graph(id="queue-chart", config={"displayModeBar": False}, style={"height": "200px"}),
                    ]
                ),
                html.Div(
                    style={"background": "#161920", "borderRadius": "10px", "padding": "16px",
                           "border": "1px solid #1e2130"},
                    children=[
                        html.P("Current Load Distribution", style={"color": "#8b90a8", "fontSize": "12px",
                                                                     "margin": "0 0 12px 0", "letterSpacing": "0.08em"}),
                        dcc.Graph(id="dist-chart", config={"displayModeBar": False}, style={"height": "200px"}),
                    ]
                ),
            ]
        ),

        # ── Migration log ─────────────────────────
        html.Div(
            style={"background": "#161920", "borderRadius": "10px", "padding": "16px",
                   "border": "1px solid #1e2130"},
            children=[
                html.P("Event Log", style={"color": "#8b90a8", "fontSize": "12px",
                                            "margin": "0 0 10px 0", "letterSpacing": "0.08em"}),
                html.Div(id="event-log", style={"fontSize": "12px", "color": "#5a5f7a",
                                                  "fontFamily": "inherit", "lineHeight": "1.8"}),
            ]
        ),

        # ── Interval timer ────────────────────────
        dcc.Interval(id="interval", interval=1000, n_intervals=0),
        dcc.Store(id="log-store", data=[]),
        dcc.Store(id="inject-store", data=0),
    ]
)


# ─────────────────────────────────────────────
# CALLBACKS
# ─────────────────────────────────────────────

@app.callback(
    Output("inject-store", "data"),
    Output("inject-feedback", "children"),
    Input("inject-btn", "n_clicks"),
    State("inject-store", "data"),
    prevent_initial_call=True,
)
def handle_inject(n_clicks, prev):
    engine.inject_task(burst_size=random.randint(8, 20))
    return n_clicks, f"✓ burst injected at {datetime.now().strftime('%H:%M:%S')}"


@app.callback(
    Output("load-chart", "figure"),
    Output("queue-chart", "figure"),
    Output("dist-chart", "figure"),
    Output("kpi-cards", "children"),
    Output("live-clock", "children"),
    Output("event-log", "children"),
    Output("log-store", "data"),
    Input("interval", "n_intervals"),
    Input("algo-dropdown", "value"),
    State("log-store", "data"),
)
def update_dashboard(n, algorithm, log_entries):
    engine.set_algorithm(algorithm)
    state = engine.get_state()

    # Update history
    history["timestamps"].append(state["timestamp"])
    for i, load in enumerate(state["loads"]):
        history["loads"][i].append(load)

    ts = list(history["timestamps"])

    # ── Line chart ──────────────────────────────
    line_fig = go.Figure()
    for i in range(NUM_PROCESSORS):
        line_fig.add_trace(go.Scatter(
            x=ts, y=list(history["loads"][i]),
            name=f"CPU {i+1}",
            line=dict(color=PROCESSOR_COLORS[i], width=1.5),
            mode="lines",
        ))
    _style_fig(line_fig, yrange=[0, 100], ytitle="%")

    # ── Queue bar chart ──────────────────────────
    queue_fig = go.Figure(go.Bar(
        x=[f"CPU {i+1}" for i in range(NUM_PROCESSORS)],
        y=state["queues"],
        marker_color=PROCESSOR_COLORS,
        marker_line_width=0,
    ))
    _style_fig(queue_fig, ytitle="tasks")

    # ── Load distribution bar ────────────────────
    dist_fig = go.Figure(go.Bar(
        x=[f"CPU {i+1}" for i in range(NUM_PROCESSORS)],
        y=[round(l, 1) for l in state["loads"]],
        marker_color=PROCESSOR_COLORS,
        marker_line_width=0,
    ))
    _style_fig(dist_fig, yrange=[0, 100], ytitle="%")

    # ── KPI cards ────────────────────────────────
    avg_load = sum(state["loads"]) / NUM_PROCESSORS
    imbalance = max(state["loads"]) - min(state["loads"])
    kpis = [
        ("Avg Load",    f"{avg_load:.1f}%",          "#4F86C6"),
        ("Imbalance",   f"{imbalance:.1f}%",          "#E07B54"),
        ("Migrations",  str(state["migrations"]),     "#9B72CF"),
        ("Tasks Done",  str(state["completed"]),      "#5BAD8F"),
    ]
    cards = [_kpi_card(label, value, color) for label, value, color in kpis]

    # ── Event log ────────────────────────────────
    new_entry = (
        f"[{state['timestamp']}]  {algorithm}  │  "
        f"avg {avg_load:.1f}%  │  imbalance {imbalance:.1f}%  │  "
        f"migrations {state['migrations']}"
    )
    log_entries = ([new_entry] + log_entries)[:8]
    log_lines = [html.Div(e, style={"borderBottom": "1px solid #1e2130", "paddingBottom": "4px"})
                 for e in log_entries]

    clock = f"last update {state['timestamp']}"
    return line_fig, queue_fig, dist_fig, cards, clock, log_lines, log_entries


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

PLOT_BG = "#161920"
GRID_COLOR = "#1e2130"
TEXT_COLOR = "#5a5f7a"

def _style_fig(fig, yrange=None, ytitle=""):
    fig.update_layout(
        paper_bgcolor=PLOT_BG,
        plot_bgcolor=PLOT_BG,
        margin=dict(l=40, r=10, t=10, b=30),
        font=dict(color=TEXT_COLOR, family="IBM Plex Mono, monospace", size=11),
        legend=dict(orientation="h", y=-0.25, font=dict(size=10)),
        showlegend=True,
        xaxis=dict(gridcolor=GRID_COLOR, linecolor=GRID_COLOR, tickfont=dict(size=10)),
        yaxis=dict(gridcolor=GRID_COLOR, linecolor=GRID_COLOR, title=ytitle,
                   range=yrange, tickfont=dict(size=10)),
    )

def _kpi_card(label, value, accent):
    return html.Div(
        style={"background": "#161920", "border": f"1px solid {accent}22",
               "borderRadius": "10px", "padding": "14px 16px"},
        children=[
            html.Div(label, style={"color": TEXT_COLOR, "fontSize": "11px",
                                    "letterSpacing": "0.08em", "marginBottom": "6px"}),
            html.Div(value, style={"color": accent, "fontSize": "22px",
                                    "fontWeight": "500", "fontFamily": "IBM Plex Mono, monospace"}),
        ]
    )


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)