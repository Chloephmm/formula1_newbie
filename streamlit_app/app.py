# F1 Race Predictor — Streamlit
# -------------------------------------------------------------------
# A dark "Pit Wall" prediction dashboard.
# Pick an as-of date -> the model finds the next Grand Prix and predicts
# qualifying + the podium, flagging whether the grid is predicted or real.
#
# Run:
#   pip install -r requirements.txt
#   streamlit run app.py
# -------------------------------------------------------------------
import base64
import json
import sys
from datetime import date, datetime
from pathlib import Path

import streamlit as st

# make the ml/ package importable (models + cached data live under ../ml)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml"))
from src.model.data import ML_DIR  # noqa: E402
from src.model.forecast import forecast  # noqa: E402

st.set_page_config(page_title="F1 Race Predictor", page_icon="🏁", layout="wide")

# ============================ DESIGN CONSTANTS ============================
TEAMS = {
    "MER": ("Mercedes",     "#00D7B6"),
    "FER": ("Ferrari",      "#E8002D"),
    "MCL": ("McLaren",      "#FF8000"),
    "RBR": ("Red Bull",     "#4B6FE0"),
    "AST": ("Aston Martin", "#22A77E"),
    "WIL": ("Williams",     "#3D8BFF"),
    "ALP": ("Alpine",       "#2BA3E0"),
    "RB":  ("Racing Bulls", "#7A93FF"),
    "SAU": ("Audi",         "#9AA2A8"),
    "HAS": ("Haas",         "#C8CDD3"),
    "CAD": ("Cadillac",     "#C9A24B"),
}

DRIVERS = {
    "ANT": "Antonelli", "RUS": "Russell", "HAM": "Hamilton", "LEC": "Leclerc",
    "NOR": "Norris", "PIA": "Piastri", "VER": "Verstappen", "TSU": "Tsunoda",
    "ALO": "Alonso", "STR": "Stroll", "SAI": "Sainz", "ALB": "Albon",
    "GAS": "Gasly", "HAD": "Hadjar", "LAW": "Lawson",
}

MEDAL = {0: "#e9b949", 1: "#c8cdd3", 2: "#cd7f3e"}
BAR_STOPS = ["#ff3b30", "#ff5b42", "#ff7a3c", "#ff9a2e", "#ffb020", "#e8a93a", "#c79a4a", "#9c8a5c"]

# ============================ LIVE ML WIRING ============================
# Map the live data's constructor_id -> the design's 3-letter team codes.
TEAM_ID2CODE = {
    "mercedes": "MER", "ferrari": "FER", "mclaren": "MCL", "red_bull": "RBR",
    "aston_martin": "AST", "williams": "WIL", "alpine": "ALP", "rb": "RB",
    "racing_bulls": "RB", "alphatauri": "RB", "sauber": "SAU", "audi": "SAU",
    "kick_sauber": "SAU", "haas": "HAS", "cadillac": "CAD",
}

COUNTRY_FLAG = {
    "Australia": "🇦🇺", "China": "🇨🇳", "Japan": "🇯🇵", "USA": "🇺🇸", "United States": "🇺🇸",
    "Bahrain": "🇧🇭", "Saudi Arabia": "🇸🇦", "Spain": "🇪🇸", "Monaco": "🇲🇨", "Canada": "🇨🇦",
    "Austria": "🇦🇹", "UK": "🇬🇧", "United Kingdom": "🇬🇧", "Belgium": "🇧🇪", "Hungary": "🇭🇺",
    "Netherlands": "🇳🇱", "Italy": "🇮🇹", "Azerbaijan": "🇦🇿", "Singapore": "🇸🇬", "Mexico": "🇲🇽",
    "Brazil": "🇧🇷", "Qatar": "🇶🇦", "UAE": "🇦🇪", "United Arab Emirates": "🇦🇪",
}


def _team_code(team_id, team_name):
    """Resolve a live constructor to a design team code (registering new teams)."""
    code = TEAM_ID2CODE.get(team_id) or (team_id or team_name or "UNK")[:3].upper()
    if code not in TEAMS:
        TEAMS[code] = (team_name or code, "#9aa0a6")
    return code


def _reg_driver(code, name):
    """Register a driver code -> short name if not already known."""
    if code and code not in DRIVERS:
        DRIVERS[code] = name.split()[-1] if name else code


def refresh_season_data(season: int):
    """Re-pull the season's data from the live F1 API (used by the Refresh button).

    After a qualifying session runs, this brings the new grid into the cache so the
    app can switch from the predicted-grid (2-stage) mode to the real-grid mode.
    """
    from src.data import cache, jolpica  # local import: only needed on refresh
    endpoints = {
        "results": jolpica.get_race_results,
        "qualifying": jolpica.get_qualifying,
        "driver_standings": jolpica.get_driver_standings,
        "constructor_standings": jolpica.get_constructor_standings,
        "schedule": jolpica.get_schedule,
    }
    for name, fn in endpoints.items():
        cache.cached(f"{name}_{season}", lambda fn=fn, s=season: fn(s), refresh=True)


@st.cache_data(show_spinner=False)
def _run_forecast(as_of_iso: str):
    """Cache the (expensive) ML forecast by date — pure data, no global mutation."""
    return forecast(as_of_iso)


def resolve(as_of_iso: str):
    """Run the live ML forecast for the next race as of the date -> (race, is_real)."""
    res = _run_forecast(as_of_iso)
    if res.get("error"):
        return None, False

    def grid(lst, n=12):
        rows = []
        for d in lst[:n]:
            _reg_driver(d["code"], d.get("driverName", ""))
            rows.append((d["code"], _team_code(d["teamId"], d["team"]), float(d["gap"])))
        return rows

    def pod(lst, n=8):
        rows = []
        for d in lst[:n]:
            _reg_driver(d["code"], d.get("driverName", ""))
            rows.append((d["code"], _team_code(d["teamId"], d["team"]),
                         int(round(d["podiumProbability"] * 100))))
        return rows

    r = res["race"]
    race = {
        "round": r["round"], "name": r["name"],
        "flag": COUNTRY_FLAG.get(r.get("country") or "", "🏁"),
        "quali": r["qualifyingDate"], "race": r["date"],
        "pred": grid(res["predictedQualifying"]),
        "podium": pod(res["preQualifyingPodium"]),
    }
    if res["hasRealGrid"]:
        race["real"] = grid(res["realQualifying"])
        race["podium_real"] = pod(res["realGridPodium"])
    return race, bool(res["hasRealGrid"])


def fmt_short(iso: str) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%a %d %b")


# ============================ STYLES ============================
def bg_data_uri(path: str) -> str:
    p = Path(__file__).parent / path
    data = base64.b64encode(p.read_bytes()).decode()
    return f"data:image/png;base64,{data}"


def inject_css():
    bg = bg_data_uri("assets/bg-sunset2.png")
    st.html(f"""
    <link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
      :root{{
        --red:#ff3b30; --amber:#ffb020; --green:#2fd16b; --yellow:#ffd23f;
        --ink:#f4f5f3; --dim:#9aa0a6; --muted:#6a6f76;
        --slate:#24272c; --line:rgba(255,255,255,.09); --line-strong:rgba(255,255,255,.16);
        --card:rgba(20,22,26,.72);
        --mono:'JetBrains Mono',ui-monospace,monospace; --sans:'Archivo',system-ui,sans-serif;
      }}
      /* fixed photo backdrop + scrim */
      .stApp{{
        background:
          radial-gradient(120% 80% at 50% 4%, transparent 34%, rgba(12,11,12,.5) 100%),
          linear-gradient(180deg, rgba(12,11,12,.72) 0%, rgba(12,11,12,.18) 22%, rgba(12,11,12,.40) 54%, rgba(12,11,12,.96) 100%),
          url("{bg}");
        background-size:cover; background-position:center top; background-attachment:fixed;
      }}
      [data-testid="stHeader"], #MainMenu, footer {{ display:none; }}
      .block-container{{ max-width:1120px; padding-top:2.2rem; padding-bottom:5rem; }}
      html, body, [class*="css"], .stMarkdown, p, span, div {{ font-family:var(--sans); color:var(--ink); }}

      /* header */
      .eyebrow{{display:flex;align-items:center;gap:11px;font-family:var(--mono);font-size:12px;letter-spacing:.34em;text-transform:uppercase;color:#ffd7b0;}}
      .eyebrow .tick{{width:30px;height:3px;background:var(--red);border-radius:2px;box-shadow:0 0 14px rgba(255,59,48,.8);}}
      .hh1{{font-size:clamp(40px,6vw,64px);font-weight:900;letter-spacing:-.025em;line-height:.96;margin:14px 0 12px;text-shadow:0 2px 30px rgba(0,0,0,.55);}}
      .hh1 .accent{{color:var(--red);}}
      .lede{{font-size:17px;line-height:1.55;color:#d6d9d4;max-width:560px;}}

      /* date input -> styled like the prototype field */
      [data-testid="stDateInput"]{{ width:max-content; }}
      [data-testid="stDateInput"] label p{{font-family:var(--mono);font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--dim);}}
      [data-testid="stDateInput"] [data-baseweb="input"], [data-testid="stDateInput"] [data-baseweb="base-input"]{{
        background:var(--slate)!important;border:1px solid var(--line-strong)!important;border-radius:11px!important;}}
      [data-testid="stDateInput"] input{{color:var(--ink)!important;font-family:var(--mono)!important;font-weight:600!important;font-size:16px!important;}}
      /* date-picker calendar popup -> keep day numbers dark & readable on white */
      [data-baseweb="calendar"], [data-baseweb="calendar"] *{{color:#15151e!important;}}
      [data-baseweb="popover"] [role="gridcell"], [data-baseweb="popover"] [role="gridcell"] *{{color:#15151e!important;}}
      [data-baseweb="calendar"] [aria-selected="true"], [data-baseweb="calendar"] [aria-selected="true"] *{{color:#ffffff!important;}}
      [data-baseweb="calendar"] [aria-disabled="true"], [data-baseweb="calendar"] [aria-disabled="true"] *{{color:#b7bcc2!important;}}
      /* refresh / run button -> match the dark theme */
      [data-testid="stButton"] button{{background:var(--slate);color:var(--ink);border:1px solid var(--line-strong);border-radius:11px;font-family:var(--mono);font-weight:800;letter-spacing:.08em;padding:.55rem 1.6rem;transition:all .2s ease;}}
      [data-testid="stButton"] button:hover{{border-color:var(--red);color:#fff;box-shadow:0 0 18px rgba(255,59,48,.25);}}
      [data-testid="stButton"] button:focus{{box-shadow:none!important;}}

      /* cards */
      .card{{background:var(--card);backdrop-filter:blur(16px) saturate(1.1);border:1px solid var(--line);border-radius:18px;}}
      .results{{display:grid;grid-template-columns:1.05fr .95fr;gap:20px;margin-top:20px;}}
      @media(max-width:820px){{.results{{grid-template-columns:1fr;}}}}
      .panel-head{{display:flex;align-items:center;gap:12px;padding:18px 24px;border-bottom:1px solid var(--line);}}
      .panel-head .ic{{width:34px;height:34px;border-radius:9px;display:grid;place-items:center;}}
      .panel-head h3{{font-size:13px;font-family:var(--mono);letter-spacing:.16em;text-transform:uppercase;font-weight:700;margin:0;}}
      .panel-head .hint{{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--muted);}}

      /* race strip */
      .race-strip{{display:flex;align-items:center;gap:16px;margin-top:30px;}}
      .race-flag{{font-size:42px;line-height:1;}}
      .race-name h2{{font-size:32px;font-weight:800;letter-spacing:-.02em;margin:0;}}
      .race-meta{{display:flex;font-family:var(--mono);font-size:12.5px;color:var(--dim);margin-top:6px;}}
      .race-meta span{{padding-right:14px;margin-right:14px;border-right:1px solid var(--line-strong);}}
      .race-meta span:last-child{{border:none;}}
      .race-meta b{{color:var(--ink);font-weight:600;}}

      /* mode badge */
      .mode{{display:flex;align-items:center;gap:13px;padding:14px 20px;border-radius:13px;font-size:14.5px;margin-top:22px;border:1px solid;}}
      .mode.pre{{background:rgba(255,210,63,.10);border-color:rgba(255,210,63,.4);color:#ffe08a;}}
      .mode.real{{background:rgba(47,209,107,.10);border-color:rgba(47,209,107,.42);color:#9bf0bf;}}
      .mode .pulse{{width:11px;height:11px;border-radius:50%;}}
      .mode.pre .pulse{{background:var(--yellow);}} .mode.real .pulse{{background:var(--green);}}
      .mode .label{{font-weight:700;}} .mode .sub{{opacity:.72;}}

      /* quali table */
      .qrow{{display:grid;grid-template-columns:34px 1fr 110px 64px;gap:10px;align-items:center;padding:11px 12px;border-radius:9px;}}
      .qhead{{display:grid;grid-template-columns:34px 1fr 110px 64px;gap:10px;padding:8px 12px;font-family:var(--mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);}}
      .qrow .pos{{font-family:var(--mono);font-weight:700;font-size:15px;text-align:center;color:var(--dim);}}
      .qrow.p1{{background:linear-gradient(90deg, rgba(255,59,48,.10), transparent 70%);}}
      .qrow.p1 .pos{{color:var(--red);}}
      .qrow .drv{{display:flex;align-items:center;gap:11px;}}
      .qrow .teambar{{width:3px;height:22px;border-radius:2px;}}
      .qrow .code{{font-weight:800;font-size:15px;}}
      .qrow .full{{color:var(--dim);font-size:13px;}}
      .qrow .team{{font-family:var(--mono);font-size:12px;color:var(--dim);}}
      .qrow .gap{{font-family:var(--mono);font-size:13px;color:var(--amber);text-align:right;font-weight:600;}}
      .qrow .gap.zero{{color:var(--red);}}
      .delta{{font-family:var(--mono);font-size:10px;padding:2px 6px;border-radius:4px;margin-left:8px;font-weight:600;}}
      .delta.up{{background:rgba(47,209,107,.16);color:var(--green);}}
      .delta.down{{background:rgba(255,59,48,.16);color:#ff7a72;}}

      /* podium */
      .podium-body{{padding:20px 24px 24px;}}
      .pchip{{display:flex;align-items:center;gap:14px;padding:14px 16px;border-radius:12px;background:rgba(255,255,255,.035);border:1px solid var(--line);margin-bottom:11px;}}
      .medal{{width:32px;height:32px;border-radius:50%;display:grid;place-items:center;font-family:var(--mono);font-weight:800;font-size:14px;color:#16130a;}}
      .pchip .who{{flex:1;}} .pchip .who .nm{{font-weight:800;font-size:16px;}}
      .pchip .who .tm{{font-family:var(--mono);font-size:12px;color:var(--dim);margin-top:2px;}}
      .pchip .prob{{font-family:var(--mono);font-weight:700;font-size:20px;}}
      .bars{{margin-top:22px;padding-top:20px;border-top:1px solid var(--line);}}
      .bars .bt{{font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin-bottom:16px;}}
      .brow{{display:grid;grid-template-columns:42px 1fr 44px;align-items:center;gap:12px;margin-bottom:12px;}}
      .brow .bl{{font-family:var(--mono);font-size:12.5px;font-weight:700;color:var(--dim);}}
      .btrack{{height:10px;border-radius:6px;background:var(--slate);overflow:hidden;}}
      .bfill{{display:block;height:100%;border-radius:6px;transform-origin:left;animation:grow .9s cubic-bezier(.22,1,.36,1);}}
      @keyframes grow{{from{{transform:scaleX(0);}}}}
      .brow .bv{{font-family:var(--mono);font-size:12.5px;font-weight:700;text-align:right;}}

      /* accuracy + disclaimer */
      .accbar{{display:flex;margin-top:14px;}}
      .accstat{{flex:1;padding:16px 18px;border-right:1px solid var(--line);}}
      .accstat:last-child{{border:none;}}
      .accstat .av{{font-family:var(--mono);font-size:24px;font-weight:700;}}
      .accstat .av .u{{font-size:13px;color:var(--dim);}}
      .accstat .ak{{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-top:5px;}}
      .disclaimer{{display:flex;gap:14px;margin-top:26px;padding:18px 22px;border-radius:13px;background:rgba(255,176,32,.06);border:1px solid rgba(255,176,32,.22);}}
      .disclaimer .wi{{color:var(--amber);font-size:18px;}}
      .disclaimer p{{font-size:13.5px;line-height:1.6;color:#d4c9b4;margin:0;}}
      .disclaimer b{{color:#ffd99a;}}

      /* compare expander (native st.expander) */
      [data-testid="stExpander"]{{background:var(--card);border:1px solid var(--line)!important;border-radius:18px!important;margin-top:20px;}}
      [data-testid="stExpander"] summary p{{font-weight:700;font-size:15px;}}
      .cmp-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;}}
      .cmp-col h5{{font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);margin:0 0 12px;}}
      .cmp-row{{display:grid;grid-template-columns:24px 1fr;gap:10px;padding:8px 0;border-bottom:1px solid var(--line);font-size:14px;}}
      .cmp-row .cp{{font-family:var(--mono);color:var(--muted);font-size:13px;}}
      .cmp-row .cd{{font-weight:700;}} .cmp-row .ct{{font-family:var(--mono);font-size:11px;color:var(--dim);margin-left:6px;}}
      .moved{{font-family:var(--mono);font-size:10px;padding:1px 5px;border-radius:3px;margin-left:6px;font-weight:600;}}
      .moved.u{{background:rgba(47,209,107,.16);color:var(--green);}}
      .moved.d{{background:rgba(255,59,48,.16);color:#ff7a72;}}
    </style>
    """)


# ============================ HTML BUILDERS ============================
def header_html() -> str:
    return """
    <div class="eyebrow"><span class="tick"></span>Season 2026 · Prediction Model</div>
    <div class="hh1">F1 Race <span class="accent">Predictor</span></div>
    <p class="lede">Pick a date. The model finds the next Grand Prix and predicts qualifying
    and the podium — flagging how much to trust it.</p>
    """


def race_strip_html(race) -> str:
    return f"""
    <div class="race-strip">
      <span class="race-flag">{race['flag']}</span>
      <div class="race-name">
        <h2>{race['name']}</h2>
        <div class="race-meta">
          <span>Round <b>{race['round']:02d}</b></span>
          <span>Race <b>{fmt_short(race['race'])}</b></span>
          <span>Quali <b>{fmt_short(race['quali'])}</b></span>
        </div>
      </div>
    </div>
    """


def mode_html(is_real: bool) -> str:
    if is_real:
        label, sub = ("Real grid confirmed",
                      "qualifying is in; the starting grid is locked and the podium model is re-run on actual positions.")
        cls = "real"
    else:
        label, sub = ("Pre-qualifying estimate",
                      "the grid itself is predicted, so this is the model's least reliable read. Expect movement after quali.")
        cls = "pre"
    return f"""<div class="mode {cls}"><span class="pulse"></span>
      <span><span class="label">{label}</span><span class="sub"> — {sub}</span></span></div>"""


def quali_html(race, is_real: bool) -> str:
    grid = race["real"] if is_real else race["pred"]
    pred_index = {r[0]: i for i, r in enumerate(race["pred"])}
    title = "Starting Grid" if is_real else "Predicted Qualifying"
    hint = "official" if is_real else "model · top 12"
    rows = ""
    for i, (code, team, gap) in enumerate(grid):
        tname, tcol = TEAMS[team]
        delta = ""
        if is_real and code in pred_index:
            mv = pred_index[code] - i
            if mv != 0:
                cls = "up" if mv > 0 else "down"
                arr = "▲" if mv > 0 else "▼"
                delta = f'<span class="delta {cls}">{arr}{abs(mv)}</span>'
        gap_txt = "POLE" if gap == 0 else f"+{gap:.2f}"
        gap_cls = " zero" if gap == 0 else ""
        rows += f"""
        <div class="qrow{' p1' if i == 0 else ''}">
          <span class="pos">{i+1}</span>
          <span class="drv"><span class="teambar" style="background:{tcol}"></span>
            <span class="code">{code}</span><span class="full">{DRIVERS.get(code,'')}</span>{delta}</span>
          <span class="team">{tname}</span>
          <span class="gap{gap_cls}">{gap_txt}</span>
        </div>"""
    icon = ('<svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M3 17l4-8 4 5 3-9 4 12" '
            'stroke="#ff5b52" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    return f"""
    <div class="card">
      <div class="panel-head"><span class="ic" style="background:rgba(255,59,48,.14)">{icon}</span>
        <h3>{title}</h3><span class="hint">{hint}</span></div>
      <div style="padding:8px 12px 14px;">
        <div class="qhead"><span style="text-align:center">P</span><span>Driver</span><span>Team</span><span style="text-align:right">Gap</span></div>
        {rows}
      </div>
    </div>"""


def podium_html(race, is_real: bool) -> str:
    podium = race["podium_real"] if (is_real and "podium_real" in race) else race["podium"]
    top3 = podium[:3]
    bars = podium[:8]
    mx = bars[0][2]
    chips = ""
    for i, (code, team, p) in enumerate(top3):
        tname, tcol = TEAMS[team]
        chips += f"""
        <div class="pchip"><span class="medal" style="background:{MEDAL[i]}">{i+1}</span>
          <span class="who"><div class="nm">{DRIVERS[code]} <span style="color:var(--muted);font-size:13px">{code}</span></div>
          <div class="tm"><span style="color:{tcol}">●</span> {tname}</div></span>
          <span class="prob" style="color:{MEDAL[i]}">{p}%</span></div>"""
    barrows = ""
    for i, (code, _team, p) in enumerate(bars):
        col = BAR_STOPS[i] if i < len(BAR_STOPS) else "#7a766a"
        barrows += f"""
        <div class="brow"><span class="bl">{code}</span>
          <span class="btrack"><span class="bfill" style="width:{p/mx*100:.1f}%;background:{col}"></span></span>
          <span class="bv">{p}%</span></div>"""
    icon = ('<svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M6 4h12v3a6 6 0 01-12 0V4z" '
            'stroke="#e9b949" stroke-width="1.8"/><path d="M9 14h6M12 14v4M9 20h6" stroke="#e9b949" '
            'stroke-width="1.8" stroke-linecap="round"/></svg>')
    return f"""
    <div class="card">
      <div class="panel-head"><span class="ic" style="background:rgba(233,185,73,.16)">{icon}</span>
        <h3>Predicted Podium</h3><span class="hint">P(top-3)</span></div>
      <div class="podium-body">{chips}
        <div class="bars"><div class="bt">Podium probability · top 8</div>{barrows}</div>
      </div>
    </div>"""


def compare_html(race) -> str:
    pred_index = {r[0]: i for i, r in enumerate(race["pred"])}
    left = "".join(
        f'<div class="cmp-row"><span class="cp">{i+1}</span><span><span class="cd">{r[0]}</span>'
        f'<span class="ct">{TEAMS[r[1]][0]}</span></span></div>'
        for i, r in enumerate(race["pred"][:8]))
    right = ""
    for i, r in enumerate(race["real"][:8]):
        mv = pred_index.get(r[0])
        tag = ""
        if mv is not None and (mv - i) != 0:
            d = mv - i
            cls = "u" if d > 0 else "d"
            arr = "▲" if d > 0 else "▼"
            tag = f'<span class="moved {cls}">{arr}{abs(d)}</span>'
        right += (f'<div class="cmp-row"><span class="cp">{i+1}</span><span><span class="cd">{r[0]}</span>'
                  f'<span class="ct">{TEAMS[r[1]][0]}</span>{tag}</span></div>')
    return f"""
    <div class="cmp-grid">
      <div class="cmp-col"><h5><span style="color:var(--yellow)">●</span> Predicted (pre-quali)</h5>{left}</div>
      <div class="cmp-col"><h5><span style="color:var(--green)">●</span> Actual grid</h5>{right}</div>
    </div>"""


def accuracy_html() -> str:
    """Real model metrics, read from the saved evaluation files (with fallbacks)."""
    grid_err, podium_hit, gap_mae, train_races = "±3.4", "70", "0.60", "182"
    try:
        qm = json.loads((ML_DIR / "models" / "quali_metrics.json").read_text())
        grid_err = f"±{qm['mean_grid_error']:.1f}"
        gap_mae = f"{qm['median_gap_mae']:.2f}"
        train_races = str(qm["train_races"])
    except Exception:
        pass
    try:
        rm = json.loads((ML_DIR.parent / "web" / "public" / "data" / "metrics.json").read_text())
        podium_hit = str(round(rm["podium"]["top3Accuracy"] * 100))
    except Exception:
        pass
    return f"""
<div class="card accbar">
  <div class="accstat"><div class="av">{grid_err}<span class="u"> pos</span></div><div class="ak">Mean grid error (pre-quali)</div></div>
  <div class="accstat"><div class="av">{podium_hit}<span class="u">%</span></div><div class="ak">Podium hit rate</div></div>
  <div class="accstat"><div class="av">{gap_mae}<span class="u">s</span></div><div class="ak">Median gap MAE</div></div>
  <div class="accstat"><div class="av">{train_races}</div><div class="ak">Races in training set</div></div>
</div>"""

DISCLAIMER_HTML = """
<div class="disclaimer"><span class="wi">⚠</span>
  <p>Probabilities are <b>calibrated estimates, not certainties</b> — F1 has crashes, safety cars and rain.
  The pre-qualifying predicted grid is on average <b>~3.4 positions off</b> per driver.
  Treat the podium bars as odds, not outcomes.</p></div>"""


# ============================ APP ============================
inject_css()
st.html(header_html())

# Selectable range: today → the final 2026 race (no past races; we predict upcoming ones).
_today = date.today()
as_of = st.date_input(
    "As-of date",
    value=_today,
    min_value=_today,
    max_value=date(2026, 12, 6),   # 2026 season finale (Abu Dhabi)
    format="YYYY-MM-DD",
)
as_of_iso = as_of.isoformat()

# Refresh button — re-fetch the latest data so "after qualifying" predictions use the
# real grid. Click it once qualifying (or the race) has run for the selected weekend.
if st.button("**RUN**",
             help="Fetch the latest results & qualifying from the F1 API, then re-predict. "
                  "Use after a qualifying session to switch to real-grid mode."):
    with st.spinner("Fetching the latest F1 data…"):
        try:
            refresh_season_data(as_of.year)
            st.cache_data.clear()
            st.session_state["refreshed_at"] = datetime.now().strftime("%H:%M:%S")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Refresh failed: {exc}")
        else:
            st.rerun()

if "refreshed_at" in st.session_state:
    st.caption(f"Data last refreshed at {st.session_state['refreshed_at']}")

race, is_real = resolve(as_of_iso)
if race is None:
    st.warning("No race data available for this date yet. Pick a 2026 in-season date, or "
               "re-fetch the data (ml: `python scripts/fetch_data.py --seasons 2026 --refresh`).")
    st.stop()

st.html(race_strip_html(race))
st.html(mode_html(is_real))

# Date is after qualifying and the real grid is loaded -> confirm it's real data.
if is_real:
    st.caption("📡 Real data from today's qualifying.")
st.html(f'<div class="results">{quali_html(race, is_real)}{podium_html(race, is_real)}</div>')

# Compare expander — only meaningful once qualifying is in
if is_real:
    with st.expander("Compare: pre-qualifying vs real grid", expanded=True):
        st.html(compare_html(race))
else:
    st.caption("Compare: pre-qualifying vs real grid — unlocks after qualifying.")

st.html(accuracy_html())
st.html(DISCLAIMER_HTML)
