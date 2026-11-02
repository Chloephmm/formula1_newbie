"""F1 saved-prediction dashboard.

Visitors only read confirmed JSON artifacts. Data ingestion, validation, training,
and publication run in GitHub Actions and are intentionally unreachable here.
"""
from __future__ import annotations

import base64
from datetime import date, datetime
import json
import os
from pathlib import Path
import sys

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit_app.prediction_data import (
    current_saved_event_id,
    read_saved_event,
)
from streamlit_app.prediction_view import render_saved_prediction


DATA_ROOT = ROOT / "web" / "public" / "data"
st.set_page_config(page_title="F1 Race Predictor", page_icon="🏁", layout="wide")


def _background() -> str:
    path = Path(__file__).parent / "assets" / "bg-sunset2.png"
    return base64.b64encode(path.read_bytes()).decode("ascii")


def inject_css() -> None:
    st.html(
        f"""
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{{--red:#ff3b30;--amber:#ffb020;--green:#2fd16b;--yellow:#ffd23f;--ink:#f4f5f3;--dim:#9aa0a6;--muted:#6a6f76;--slate:#24272c;--line:rgba(255,255,255,.09);--line-strong:rgba(255,255,255,.16);--card:rgba(20,22,26,.72);--mono:'JetBrains Mono',ui-monospace,monospace;--sans:'Archivo',system-ui,sans-serif}}
.stApp{{background:radial-gradient(120% 80% at 50% 4%,transparent 34%,rgba(12,11,12,.5) 100%),linear-gradient(180deg,rgba(12,11,12,.72) 0%,rgba(12,11,12,.18) 22%,rgba(12,11,12,.40) 54%,rgba(12,11,12,.96) 100%),url("data:image/png;base64,{_background()}");background-size:cover;background-position:center top;background-attachment:fixed}}
[data-testid="stHeader"],#MainMenu,footer{{display:none}}.block-container{{max-width:1120px;padding-top:1.6rem;padding-bottom:5rem}}html,body,[class*="css"],.stMarkdown,p,span,div{{font-family:var(--sans);color:var(--ink)}}
.eyebrow{{display:flex;align-items:center;gap:11px;font-family:var(--mono);font-size:12px;letter-spacing:.34em;text-transform:uppercase;color:#ffd7b0}}.eyebrow .tick{{width:30px;height:3px;background:var(--red);border-radius:2px}}.hh1{{font-size:clamp(40px,6vw,64px);font-weight:900;letter-spacing:-.025em;line-height:.96;margin:14px 0 12px}}.hh1 .accent{{color:var(--red)}}.lede{{font-size:17px;line-height:1.55;color:#d6d9d4;max-width:650px}}
[data-testid="stDateInput"] label p,[data-testid="stToggle"] label p{{font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim)}}[data-testid="stDateInput"] [data-baseweb="input"],[data-testid="stDateInput"] [data-baseweb="base-input"]{{background:var(--slate)!important;border:1px solid var(--line-strong)!important;border-radius:11px!important}}[data-testid="stDateInput"] input{{color:var(--ink)!important;font-family:var(--mono)!important;font-weight:600!important}}[data-baseweb="calendar"],[data-baseweb="calendar"] *{{color:#15151e!important}}
.card{{background:var(--card);backdrop-filter:blur(16px) saturate(1.1);border:1px solid var(--line);border-radius:18px}}.results{{display:grid;grid-template-columns:1.05fr .95fr;gap:20px;margin-top:12px}}@media(max-width:820px){{.results{{grid-template-columns:1fr}}}}.panel-head{{display:flex;align-items:center;gap:12px;padding:18px 24px;border-bottom:1px solid var(--line)}}.panel-head .ic{{width:34px;height:34px;border-radius:9px;display:grid;place-items:center}}.panel-head h3{{font-size:13px;font-family:var(--mono);letter-spacing:.16em;text-transform:uppercase;font-weight:700;margin:0}}.panel-head .hint{{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--muted)}}
.race-strip{{display:flex;align-items:center;gap:16px;margin-top:12px}}.race-flag{{font-size:42px;line-height:1}}.race-name h2{{font-size:32px;font-weight:800;letter-spacing:-.02em;margin:0}}.race-meta{{display:flex;font-family:var(--mono);font-size:12.5px;color:var(--dim);margin-top:6px}}.race-meta span{{padding-right:14px;margin-right:14px;border-right:1px solid var(--line-strong)}}.race-meta span:last-child{{border:none}}.race-meta b{{color:var(--ink);font-weight:600}}
.mode{{display:flex;align-items:center;gap:13px;padding:14px 20px;border-radius:13px;font-size:14.5px;margin-top:6px;border:1px solid}}.mode.pre{{background:rgba(255,210,63,.10);border-color:rgba(255,210,63,.4);color:#ffe08a}}.mode.real{{background:rgba(47,209,107,.10);border-color:rgba(47,209,107,.42);color:#9bf0bf}}.mode .pulse{{width:11px;height:11px;border-radius:50%}}.mode.pre .pulse{{background:var(--yellow)}}.mode.real .pulse{{background:var(--green)}}.mode .label{{font-weight:700}}.mode .sub{{opacity:.72}}
.qrow{{display:grid;grid-template-columns:34px 1fr 110px 64px;gap:10px;align-items:center;padding:11px 12px;border-radius:9px}}.qhead{{display:grid;grid-template-columns:34px 1fr 110px 64px;gap:10px;padding:8px 12px;font-family:var(--mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}}.qrow .pos{{font-family:var(--mono);font-weight:700;font-size:15px;text-align:center;color:var(--dim)}}.qrow.p1{{background:linear-gradient(90deg,rgba(255,59,48,.10),transparent 70%)}}.qrow.p1 .pos{{color:var(--red)}}.qrow .drv{{display:flex;align-items:center;gap:11px}}.qrow .teambar{{width:3px;height:22px;border-radius:2px}}.qrow .code{{font-weight:800;font-size:15px}}.qrow .full{{color:var(--dim);font-size:13px}}.qrow .team{{font-family:var(--mono);font-size:12px;color:var(--dim)}}.qrow .gap{{font-family:var(--mono);font-size:13px;color:var(--amber);text-align:right;font-weight:600}}.qrow .gap.zero{{color:var(--red)}}.delta{{font-family:var(--mono);font-size:10px;padding:2px 6px;border-radius:4px;margin-left:8px;font-weight:600}}.delta.up{{background:rgba(47,209,107,.16);color:var(--green)}}.delta.down{{background:rgba(255,59,48,.16);color:#ff7a72}}
.podium-body{{padding:20px 24px 24px}}.pchip{{display:flex;align-items:center;gap:14px;padding:14px 16px;border-radius:12px;background:rgba(255,255,255,.035);border:1px solid var(--line);margin-bottom:11px}}.medal{{width:32px;height:32px;border-radius:50%;display:grid;place-items:center;font-family:var(--mono);font-weight:800;font-size:14px;color:#16130a}}.pchip .who{{flex:1}}.pchip .who .nm{{font-weight:800;font-size:16px}}.pchip .who .tm{{font-family:var(--mono);font-size:12px;color:var(--dim);margin-top:2px}}.pchip .prob{{font-family:var(--mono);font-weight:700;font-size:20px}}.bars{{margin-top:22px;padding-top:20px;border-top:1px solid var(--line)}}.bars .bt{{font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin-bottom:16px}}.brow{{display:grid;grid-template-columns:42px 1fr 44px;align-items:center;gap:12px;margin-bottom:12px}}.brow .bl{{font-family:var(--mono);font-size:12.5px;font-weight:700;color:var(--dim)}}.btrack{{height:10px;border-radius:6px;background:var(--slate);overflow:hidden}}.bfill{{display:block;height:100%;border-radius:6px}}.brow .bv{{font-family:var(--mono);font-size:12.5px;font-weight:700;text-align:right}}
.cmp-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.cmp-col h5{{font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim)}}.cmp-row{{display:grid;grid-template-columns:24px 1fr;gap:10px;padding:8px 0;border-bottom:1px solid var(--line);font-size:14px}}.cmp-row .cp{{font-family:var(--mono);color:var(--muted)}}[data-testid="stExpander"]{{background:var(--card);border:1px solid var(--line)!important;border-radius:18px!important;margin-top:12px}}
.accbar{{display:flex;margin-top:14px}}.accstat{{flex:1;padding:16px 18px;border-right:1px solid var(--line)}}.accstat:last-child{{border:none}}.accstat .av{{font-family:var(--mono);font-size:24px;font-weight:700}}.accstat .u{{font-size:13px;color:var(--dim)}}.accstat .ak{{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-top:5px}}.disclaimer{{display:flex;gap:14px;margin-top:14px;padding:18px 22px;border-radius:13px;background:rgba(255,176,32,.06);border:1px solid rgba(255,176,32,.22)}}.disclaimer p{{font-size:13.5px;line-height:1.6;color:#d4c9b4;margin:0}}
</style>
"""
    )


def header_html() -> str:
    return """
<div class="eyebrow"><span class="tick"></span>Season 2026 · Saved ML forecast</div>
<div class="hh1">F1 Race <span class="accent">Predictor</span></div>
<p class="lede">Predictions update automatically from validated saved qualifying data.
This page never fetches F1 data or trains a model for a visitor.</p>
"""


def _saved_event_for_date(selected: date) -> str | None:
    try:
        races = json.loads((DATA_ROOT / "races.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    candidates = []
    for race in races:
        try:
            race_date = date.fromisoformat(race["date"])
            if race_date >= selected:
                candidates.append((race_date, int(race["season"]), int(race["round"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not candidates:
        return None
    _, season, round_number = min(candidates)
    return f"{season}-{round_number}"


def accuracy_html() -> str:
    grid_error, podium_hit, gap_mae, races = "±3.5", "70", "0.58", "54"
    try:
        metrics = json.loads(
            (ROOT / "ml" / "models" / "live_metrics.json").read_text(
                encoding="utf-8"
            )
        )
        qualifying = metrics["quali"]["2024-2026"]
        podium = metrics["podium"]["2024-2026"]
        grid_error = f"±{qualifying['c_grid_err']:.1f}"
        gap_mae = f"{qualifying['c_gap_mae']:.2f}"
        podium_hit = str(round(podium["c_podium"] * 100))
        races = str(qualifying["races"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        pass
    return f"""
<div class="card accbar"><div class="accstat"><div class="av">{grid_error}<span class="u"> pos</span></div><div class="ak">Mean grid error (pre-qualifying)</div></div>
<div class="accstat"><div class="av">{podium_hit}<span class="u">%</span></div><div class="ak">Podium hit rate</div></div>
<div class="accstat"><div class="av">{gap_mae}<span class="u">s</span></div><div class="ak">Median gap MAE</div></div>
<div class="accstat"><div class="av">{races}</div><div class="ak">Retrospective backtest races</div></div></div>
"""


@st.fragment(run_every="60s")
def forecast_panel() -> None:
    disk_feed = os.environ.get("PREDICTION_FEED_FILE")
    current_id = current_saved_event_id(disk_path=disk_feed)
    race_dates = []
    try:
        race_dates = [
            date.fromisoformat(item["date"])
            for item in json.loads((DATA_ROOT / "races.json").read_text(encoding="utf-8"))
            if item.get("date")
        ]
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        pass
    minimum = min(race_dates) if race_dates else date(2026, 1, 1)
    maximum = max(race_dates) if race_dates else date(2026, 12, 31)
    today = date.today()
    default_date = min(max(today, minimum), maximum)
    controls = st.columns([2, 2, 4], vertical_alignment="bottom")
    with controls[0]:
        follow_current = st.toggle("Follow current saved event", value=True)
    with controls[1]:
        selected = st.date_input(
            "Saved forecast date",
            value=default_date,
            min_value=minimum,
            max_value=maximum,
            format="YYYY-MM-DD",
            disabled=follow_current,
        )
    event_id = current_id if follow_current else _saved_event_for_date(selected)
    if event_id is None:
        st.warning("Prediction temporarily unavailable")
        return
    event, prediction, status = read_saved_event(
        event_id,
        disk_path=disk_feed,
    )
    render_saved_prediction(event, prediction, status)


inject_css()
st.html(header_html())
forecast_panel()
st.html(accuracy_html())
st.caption(
    "The accuracy figures are retrospective walk-forward benchmarks. Frozen saved "
    "forecasts are scored separately once completed results are available."
)
st.html(
    '<div class="disclaimer"><span>⚠</span><p>Saved podium values are normalized '
    "model estimates, not certainties. Actual qualifying is not the penalty-adjusted "
    "starting grid.</p></div>"
)
