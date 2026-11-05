"""Read-only F1 prediction dashboard backed by scheduled JSON publication."""
from __future__ import annotations

import base64
import ipaddress
import json
import os
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from streamlit_app.prediction_feed import FeedError, choose_race, load_race_results
from streamlit_app.confirmed_feed import load_bundle, load_index, retain_latest_bundle

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
DATA_ROOT = REPO_ROOT / "web" / "public" / "data"
DEPLOYED_FEED_BASE_URL = "https://raw.githubusercontent.com/Chloephmm/formula1_newbie/main/web/public/data"

st.set_page_config(page_title="F1 Race Predictor", page_icon="🏁", layout="wide")

TEAMS = {
    "MER": ("Mercedes", "#00D7B6"),
    "FER": ("Ferrari", "#E8002D"),
    "MCL": ("McLaren", "#FF8000"),
    "RBR": ("Red Bull", "#4B6FE0"),
    "AST": ("Aston Martin", "#22A77E"),
    "WIL": ("Williams", "#3D8BFF"),
    "ALP": ("Alpine", "#2BA3E0"),
    "RB": ("Racing Bulls", "#7A93FF"),
    "SAU": ("Audi", "#9AA2A8"),
    "HAS": ("Haas", "#C8CDD3"),
    "CAD": ("Cadillac", "#C9A24B"),
}

DRIVERS = {
    "ANT": "Antonelli", "RUS": "Russell", "HAM": "Hamilton", "LEC": "Leclerc",
    "NOR": "Norris", "PIA": "Piastri", "VER": "Verstappen", "TSU": "Tsunoda",
    "ALO": "Alonso", "STR": "Stroll", "SAI": "Sainz", "ALB": "Albon",
    "GAS": "Gasly", "HAD": "Hadjar", "LAW": "Lawson",
}

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

MEDAL = {0: "#e9b949", 1: "#c8cdd3", 2: "#cd7f3e"}
BAR_STOPS = ["#ff3b30", "#ff5b42", "#ff7a3c", "#ff9a2e", "#ffb020", "#e8a93a", "#c79a4a", "#9c8a5c"]


def _feed_base_url() -> str | None:
    """Use the confirmation origin in deployment and local JSON in development."""
    feed_url = os.getenv("PREDICTION_FEED_URL", "").strip()
    if feed_url:
        return feed_url.removesuffix('/prediction_feed.json')
    configured = os.getenv("PREDICTION_FEED_BASE_URL", "").strip()
    if configured:
        return configured
    try:
        hostname = (urlparse(st.context.url).hostname or "").lower()
    except (AttributeError, RuntimeError):
        hostname = ""
    if hostname in {"", "localhost", "127.0.0.1", "::1", "testserver"}:
        return None
    try:
        if ipaddress.ip_address(hostname).is_private:
            return None
    except ValueError:
        pass
    return DEPLOYED_FEED_BASE_URL


def _team_code(team_id: str | None, team_name: str | None) -> str:
    code = TEAM_ID2CODE.get(team_id or "") or (team_id or team_name or "UNK")[:3].upper()
    if code not in TEAMS:
        TEAMS[code] = (team_name or code, "#9aa0a6")
    return code


def _reg_driver(code: str, name: str) -> None:
    if code and code not in DRIVERS:
        DRIVERS[code] = name.split()[-1] if name else code


def _utc(value: str | None) -> str:
    if not value:
        return "Not scheduled"
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        return f"{timestamp:%A %m/%d/%Y} {timestamp.hour}:{timestamp:%M} UTC"
    except ValueError:
        return value


def _reason(value: str | None) -> str:
    if not value or value == "actual_qualifying_not_checked_yet":
        return "Actual qualifying results: Not available."
    if value.startswith("qualifying_unavailable_or_invalid"):
        return "Actual qualifying results: Not available or incomplete."
    return {
        "five_hour_wait_exceeds_cutoff": "The five-hour wait extends beyond the publication cutoff.",
        "insufficient_processing_buffer": "There is not enough time to publish before the cutoff.",
        "processing_window_closed": "The processing window closed before a safe update could finish.",
    }.get(value, value.replace("_", " ").capitalize() + ".")


def _short_date(value: str | None) -> str:
    if not value:
        return "TBD"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%a %m/%d")
    except ValueError:
        return value


def _race_view(artifact: dict) -> tuple[dict, bool]:
    forecast = artifact["forecast"]
    source = artifact.get("race") or forecast["race"]
    actual = artifact["input_mode"] == "actual_qualifying"

    def grid(rows: list[dict] | None, limit: int = 12) -> list[tuple[str, str, float]]:
        result = []
        for row in (rows or [])[:limit]:
            code = row.get("code", "")
            _reg_driver(code, row.get("driverName", ""))
            gap = row.get("gap")
            result.append((code, _team_code(row.get("teamId"), row.get("team")),
                           None if gap is None else float(gap)))
        return result

    def podium(rows: list[dict] | None, limit: int = 8) -> list[tuple[str, str, int]]:
        result = []
        for row in (rows or [])[:limit]:
            code = row.get("code", "")
            _reg_driver(code, row.get("driverName", ""))
            result.append((
                code,
                _team_code(row.get("teamId"), row.get("team")),
                int(round(float(row.get("podiumProbability", 0)) * 100)),
            ))
        return result

    race = {
        "round": int(source["round"]),
        "name": source["name"],
        "flag": COUNTRY_FLAG.get(source.get("country") or "", "🏁"),
        "country": source.get("country") or "",
        "quali": source.get("qualifyingStartAt") or source.get("qualifyingDate"),
        "race": source.get("raceStartAt") or source.get("date"),
        "pred": grid(forecast.get("predictedQualifying")),
        "podium": podium(forecast.get("preQualifyingPodium")),
    }
    if actual:
        race["real"] = grid(forecast.get("actualQualifying"))
        race['official_positions'] = {row.get('code', ''): row.get('position')
                                      for row in forecast.get('actualQualifying') or []}
        race["podium_real"] = podium(forecast.get("actualQualifyingPodium"))
    return race, actual


def bg_data_uri(path: str) -> str:
    data = base64.b64encode((APP_DIR / path).read_bytes()).decode()
    return f"data:image/png;base64,{data}"


def inject_css() -> None:
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
      .stApp{{
        background:
          radial-gradient(120% 80% at 50% 4%, transparent 34%, rgba(12,11,12,.5) 100%),
          linear-gradient(180deg, rgba(12,11,12,.72) 0%, rgba(12,11,12,.18) 22%, rgba(12,11,12,.40) 54%, rgba(12,11,12,.96) 100%),
          url("{bg}");
        background-size:cover; background-position:center top; background-attachment:fixed;
      }}
      [data-testid="stHeader"], #MainMenu, footer {{ display:none; }}
      .block-container{{ max-width:1120px; padding-top:1.6rem; padding-bottom:5rem; }}
      html, body, [class*="css"], .stMarkdown, p, span, div {{ font-family:var(--sans); color:var(--ink); }}
      [data-testid="stVerticalBlock"]{{ gap:.2rem; }}
      [data-testid="stElementContainer"]{{ margin:0; }}
      .lede{{ margin-bottom:0; }}

      .eyebrow{{display:flex;align-items:center;gap:11px;font-family:var(--mono);font-size:12px;letter-spacing:.34em;text-transform:uppercase;color:#ffd7b0;}}
      .eyebrow .tick{{width:30px;height:3px;background:var(--red);border-radius:2px;box-shadow:0 0 14px rgba(255,59,48,.8);}}
      .hh1{{font-size:clamp(40px,6vw,64px);font-weight:900;letter-spacing:-.025em;line-height:.96;margin:14px 0 12px;text-shadow:0 2px 30px rgba(0,0,0,.55);}}
      .hh1 .accent{{color:var(--red);}}
      .lede{{font-size:17px;line-height:1.55;color:#d6d9d4;max-width:560px;}}

      [data-testid="stHorizontalBlock"]{{ gap:.5rem; }}
      [data-testid="stSelectbox"] label{{margin-bottom:2px;}}
      [data-testid="stSelectbox"] label p{{font-family:var(--mono);font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--dim);}}
      [data-testid="stSelectbox"] [data-baseweb="select"] > div{{
        height:64px;min-height:64px;box-sizing:border-box;background:var(--slate)!important;border:1px solid var(--line-strong)!important;border-radius:11px!important;
        color:var(--ink)!important;font-family:var(--mono)!important;font-weight:600!important;font-size:15px!important;
      }}
      [data-testid="stSelectbox"] svg{{fill:var(--dim)!important;}}
      [data-testid="stSelectbox"] div[value]{{height:auto!important;}}
      .control-status{{margin:0;height:64px;box-sizing:border-box;padding:6px 10px;border-radius:11px;background:var(--slate);border:1px solid var(--line-strong);display:flex;flex-direction:column;justify-content:center;}}
      .st-key-archive_view_control [data-baseweb="select"] > div{{height:48px!important;min-height:48px!important;}}
      .control-status.actual{{border-left:3px solid var(--green);}}
      .control-status.estimated{{border-left:3px solid var(--yellow);}}
      .control-status b{{font-size:13px;line-height:1.25;}}
      .control-status span{{font-size:11.5px;line-height:1.35;color:#c9ccc8;}}
      @media(min-width:641px) and (max-width:900px){{
        .st-key-prediction_controls [data-testid="stColumn"]:nth-child(1){{flex:2!important;min-width:0!important;}}
        .st-key-prediction_controls [data-testid="stColumn"]:nth-child(2){{flex:3!important;min-width:0!important;}}
        .st-key-prediction_controls [data-testid="stColumn"]:last-child{{display:none;}}
      }}
      @media(max-width:420px){{
        .st-key-prediction_controls [data-baseweb="select"] > div{{height:80px;min-height:80px;}}
        .control-status{{height:80px;}}
      }}

      .card{{background:var(--card);backdrop-filter:blur(16px) saturate(1.1);border:1px solid var(--line);border-radius:18px;}}
      .results{{display:grid;grid-template-columns:1.05fr .95fr;gap:20px;margin-top:12px;}}
      @media(max-width:820px){{.results{{grid-template-columns:1fr;}}}}
      .panel-head{{display:flex;align-items:center;gap:12px;padding:18px 24px;border-bottom:1px solid var(--line);}}
      .panel-head .ic{{width:34px;height:34px;border-radius:9px;display:grid;place-items:center;}}
      .panel-head h3{{font-size:13px;font-family:var(--mono);letter-spacing:.16em;text-transform:uppercase;font-weight:700;margin:0;}}
      .panel-head .hint{{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--muted);}}

      .race-strip{{display:flex;align-items:center;gap:16px;margin-top:2px;}}
      .race-flag{{font-size:42px;line-height:1;}}
      .race-flag img{{display:block;width:52px;height:36px;object-fit:contain;}}
      .finish-row{{display:grid;grid-template-columns:34px minmax(100px,1fr) minmax(80px,1fr) 44px 80px;gap:10px;align-items:center;padding:11px 12px;border-bottom:1px solid var(--line);font-size:13px;}}
      .finish-row .position,.finish-row .points{{font-family:var(--mono);font-weight:700;}}
      .finish-row .result-status{{font-size:12px;color:var(--dim);}}
      .finish-table{{overflow-x:auto;}}
      .finish-table .finish-row{{min-width:420px;}}
      .race-name h2{{font-size:32px;font-weight:800;letter-spacing:-.02em;margin:0;}}
      .race-meta{{display:flex;font-family:var(--mono);font-size:12.5px;color:var(--dim);margin-top:6px;}}
      .race-meta span{{padding-right:14px;margin-right:14px;border-right:1px solid var(--line-strong);}}
      .race-meta span:last-child{{border:none;}}
      .race-meta b{{color:var(--ink);font-weight:600;}}

      .mode{{display:flex;align-items:center;gap:13px;padding:14px 20px;border-radius:13px;font-size:14.5px;margin-top:6px;border:1px solid;}}
      .mode.pre{{background:rgba(255,210,63,.10);border-color:rgba(255,210,63,.4);color:#ffe08a;}}
      .mode.real{{background:rgba(47,209,107,.10);border-color:rgba(47,209,107,.42);color:#9bf0bf;}}
      .mode .pulse{{width:11px;height:11px;border-radius:50%;}}
      .mode.pre .pulse{{background:var(--yellow);}} .mode.real .pulse{{background:var(--green);}}
      .mode .label{{font-weight:700;}} .mode .sub{{opacity:.72;}}

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

      .accbar{{display:flex;margin-top:14px;}}
      .accstat{{flex:1;padding:16px 18px;border-right:1px solid var(--line);}}
      .accstat:last-child{{border:none;}}
      .accstat .av{{font-family:var(--mono);font-size:24px;font-weight:700;}}
      .accstat .av .u{{font-size:13px;color:var(--dim);}}
      .accstat .ak{{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-top:5px;}}
      .disclaimer{{display:flex;gap:14px;margin-top:14px;padding:18px 22px;border-radius:13px;background:rgba(255,176,32,.06);border:1px solid rgba(255,176,32,.22);}}
      .disclaimer .wi{{color:var(--amber);font-size:18px;}}
      .disclaimer p{{font-size:13.5px;line-height:1.6;color:#d4c9b4;margin:0;}}
      .disclaimer b{{color:#ffd99a;}}

      [data-testid="stExpander"]{{background:var(--card);border:1px solid var(--line)!important;border-radius:18px!important;margin-top:12px;}}
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


def header_html() -> str:
    return """
    <div class="eyebrow"><span class="tick"></span>Season 2026 · Prediction Model</div>
    <div class="hh1">F1 Race <span class="accent">Predictor</span></div>
    <p class="lede">Pick a race. The model predicts qualifying and the podium —
    flagging how much to trust it.</p>
    """


def status_html(artifact: dict, status: dict | None, historical: bool) -> str:
    actual = artifact["input_mode"] == "actual_qualifying"
    frozen = bool(artifact.get("frozen_at"))
    label = "Using Actual Qualifying Result." if actual else "Using Predicted Qualifying Result."
    if historical or frozen:
        detail = f"Prediction published: {_utc(artifact.get('publication_confirmed_at') or artifact.get('prediction_updated_at'))}"
        timing = f"Publication cutoff: {_utc(artifact.get('publication_cutoff_at'))}"
    elif actual:
        detail = f"Prediction updated: {_utc(artifact.get('prediction_updated_at'))}"
        timing = f"Last data check: {_utc((status or {}).get('last_data_check_at'))}"
    else:
        detail = _reason((status or {}).get("status_reason") or artifact.get("status_reason"))
        timing = f"Next scheduled check: {_utc((status or {}).get('next_scheduled_check_at'))}"
    kind = "actual" if actual else "estimated"
    return f'<div class="control-status {kind}"><b>{label}</b><span>{detail}</span><span>{timing}</span></div>'


def flag_html(country: str) -> str:
    emoji = COUNTRY_FLAG.get(country, "")
    if len(emoji) != 2:
        return '<span role="img" aria-label="Race">🏁</span>'
    code = "".join(chr(ord(char) - 0x1F1E6 + ord("a")) for char in emoji)
    asset = REPO_ROOT / "web" / "public" / "images" / "flags" / f"{code}.svg"
    if asset.is_file():
        src = "data:image/svg+xml;base64," + base64.b64encode(asset.read_bytes()).decode()
    else:
        src = f"https://flagcdn.com/{code}.svg"
    return f'<img src="{src}" alt="{escape(country)} flag" width="52" height="36">'


def race_strip_html(race: dict) -> str:
    return f"""
    <div class="race-strip">
      <span class="race-flag">{flag_html(race['country'])}</span>
      <div class="race-name">
        <h2>{race['name']}</h2>
        <div class="race-meta">
          <span>Round <b>{race['round']:02d}</b></span>
          <span>Quali <b>{_short_date(race['quali'])}</b></span>
          <span>Race <b>{_short_date(race['race'])}</b></span>
        </div>
      </div>
    </div>
    """


def mode_html(actual: bool, frozen: bool = False) -> str:
    if actual:
        label = "Using actual qualifying results"
        sub = "validated qualifying classification is in and the podium model has been updated."
        cls = "real"
    else:
        label = "Using estimated qualifying results"
        sub = "the qualifying order is predicted, so expect movement after qualifying."
        cls = "pre"
    if frozen:
        sub = "archived prediction; these saved forecast values will not change."
    return f"""<div class="mode {cls}"><span class="pulse"></span>
      <span><span class="label">{label}</span><span class="sub"> — {sub}</span></span></div>"""


def quali_html(race: dict, actual: bool) -> str:
    grid = race["real"] if actual else race["pred"]
    pred_index = {row[0]: index for index, row in enumerate(race["pred"])}
    title = "Actual Qualifying" if actual else "Predicted Qualifying"
    hint = "validated results" if actual else "model · top 12"
    rows = ""
    for index, (code, team, gap) in enumerate(grid):
        team_name, team_color = TEAMS[team]
        position = race.get('official_positions', {}).get(code, index + 1) if actual else index + 1
        delta = ""
        if actual and position is not None and code in pred_index:
            movement = pred_index[code] + 1 - position
            if movement:
                delta_class = "up" if movement > 0 else "down"
                arrow = "▲" if movement > 0 else "▼"
                delta = f'<span class="delta {delta_class}">{arrow}{abs(movement)}</span>'
        gap_text = "No time" if gap is None else "REF" if gap == 0 else f"+{gap:.2f}"
        gap_class = " zero" if gap == 0 else ""
        rows += f"""
        <div class="qrow{' p1' if position == 1 else ''}">
          <span class="pos">{position if position is not None else '—'}</span>
          <span class="drv"><span class="teambar" style="background:{team_color}"></span>
            <span class="code">{code}</span><span class="full">{DRIVERS.get(code, '')}</span>{delta}</span>
          <span class="team">{team_name}</span>
          <span class="gap{gap_class}">{gap_text}</span>
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


def podium_html(race: dict, actual: bool) -> str:
    podium = race["podium_real"] if actual and race.get("podium_real") else race["podium"]
    top_three = podium[:3]
    bars = podium[:8]
    maximum = max((row[2] for row in bars), default=1) or 1
    chips = ""
    for index, (code, team, probability) in enumerate(top_three):
        team_name, team_color = TEAMS[team]
        chips += f"""
        <div class="pchip"><span class="medal" style="background:{MEDAL[index]}">{index + 1}</span>
          <span class="who"><div class="nm">{DRIVERS.get(code, code)} <span style="color:var(--muted);font-size:13px">{code}</span></div>
          <div class="tm"><span style="color:{team_color}">●</span> {team_name}</div></span>
          <span class="prob" style="color:{MEDAL[index]}">{probability}%</span></div>"""
    bar_rows = ""
    for index, (code, _team, probability) in enumerate(bars):
        color = BAR_STOPS[index] if index < len(BAR_STOPS) else "#7a766a"
        bar_rows += f"""
        <div class="brow"><span class="bl">{code}</span>
          <span class="btrack"><span class="bfill" style="width:{probability / maximum * 100:.1f}%;background:{color}"></span></span>
          <span class="bv">{probability}%</span></div>"""
    icon = ('<svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M6 4h12v3a6 6 0 01-12 0V4z" '
            'stroke="#e9b949" stroke-width="1.8"/><path d="M9 14h6M12 14v4M9 20h6" stroke="#e9b949" '
            'stroke-width="1.8" stroke-linecap="round"/></svg>')
    return f"""
    <div class="card">
      <div class="panel-head"><span class="ic" style="background:rgba(233,185,73,.16)">{icon}</span>
        <h3>Predicted Podium</h3><span class="hint">P(top-3)</span></div>
      <div class="podium-body">{chips}
        <div class="bars"><div class="bt">Podium probability · top 8</div>{bar_rows}</div>
      </div>
    </div>"""


def compare_html(race: dict) -> str:
    predicted_index = {row[0]: index for index, row in enumerate(race["pred"])}
    left = "".join(
        f'<div class="cmp-row"><span class="cp">{index + 1}</span><span><span class="cd">{row[0]}</span>'
        f'<span class="ct">{TEAMS[row[1]][0]}</span></span></div>'
        for index, row in enumerate(race["pred"][:8])
    )
    right = ""
    for index, row in enumerate(race["real"][:8]):
        predicted = predicted_index.get(row[0])
        tag = ""
        if predicted is not None and predicted != index:
            movement = predicted - index
            cls = "u" if movement > 0 else "d"
            arrow = "▲" if movement > 0 else "▼"
            tag = f'<span class="moved {cls}">{arrow}{abs(movement)}</span>'
        right += (f'<div class="cmp-row"><span class="cp">{index + 1}</span><span><span class="cd">{row[0]}</span>'
                  f'<span class="ct">{TEAMS[row[1]][0]}</span>{tag}</span></div>')
    return f"""
    <div class="cmp-grid">
      <div class="cmp-col"><h5><span style="color:var(--yellow)">●</span> Estimated qualifying</h5>{left}</div>
      <div class="cmp-col"><h5><span style="color:var(--green)">●</span> Actual qualifying</h5>{right}</div>
    </div>"""


def accuracy_html() -> str:
    grid_error, podium_hit, gap_mae, race_count = "±3.5", "70", "0.58", "54"
    try:
        metrics = json.loads((REPO_ROOT / "ml" / "models" / "live_metrics.json").read_text())
        qualifying = metrics["quali"]["2024-2026"]
        podium = metrics["podium"]["2024-2026"]
        grid_error = f"±{qualifying['c_grid_err']:.1f}"
        gap_mae = f"{qualifying['c_gap_mae']:.2f}"
        podium_hit = str(round(podium["c_podium"] * 100))
        race_count = str(qualifying["races"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        pass
    return f"""
<div class="card accbar">
  <div class="accstat"><div class="av">{grid_error}<span class="u"> pos</span></div><div class="ak">Mean qualifying error (estimated)</div></div>
  <div class="accstat"><div class="av">{podium_hit}<span class="u">%</span></div><div class="ak">Podium hit rate</div></div>
  <div class="accstat"><div class="av">{gap_mae}<span class="u">s</span></div><div class="ak">Median gap MAE</div></div>
  <div class="accstat"><div class="av">{race_count}</div><div class="ak">Backtested races (’24–’26)</div></div>
</div>"""


DISCLAIMER_HTML = """
<div class="disclaimer"><span class="wi">⚠</span>
  <p>Probabilities are <b>calibrated estimates, not certainties</b> — F1 has crashes, safety cars and rain.
  The estimated qualifying order is on average <b>~3.5 positions off</b> per driver.
  Treat the podium bars as odds, not outcomes.</p></div>"""


def _render_dashboard(artifact: dict) -> None:
    race, actual = _race_view(artifact)
    st.html(race_strip_html(race))
    st.html(mode_html(actual, bool(artifact.get("frozen_at"))))
    st.html(f'<div class="results">{quali_html(race, actual)}{podium_html(race, actual)}</div>')
    if actual and race['pred']:
        with st.expander("Compare: estimated vs actual qualifying results", expanded=True):
            st.html(compare_html(race))
    elif artifact.get("frozen_at"):
        st.caption("No prediction using actual qualifying results was saved for this race.")
    else:
        st.caption("Compare: estimated vs actual qualifying results — unlocks after qualifying.")
    st.html(accuracy_html())
    st.caption('Accuracy bar: historical reconstruction benchmark, not archived live forecast accuracy. '
               'Podium values are normalized estimates. Qualifying positions are not the penalty-adjusted starting grid.')
    if artifact.get('publication_confirmed'):
        st.caption(f"Saved prediction ID: {artifact['prediction_id']} · "
                   f"Publication confirmed: {_utc(artifact.get('publication_confirmed_at'))} · "
                   f"Feed updated: {_utc(artifact.get('feed_updated_at'))}")
    else:
        st.caption('Legacy saved forecast: publication confirmation was not recorded; excluded from confirmed live evaluation.')
    st.caption("📈 The model is retrained by scheduled background jobs. The figures above are its "
               "2024–26 walk-forward backtest, with each race scored only on earlier data.")
    st.html(DISCLAIMER_HTML)


def _render_race_results(artifact: dict, feed_base_url: str | None) -> None:
    race, _ = _race_view(artifact)
    st.html(race_strip_html(race))
    race_id = artifact["race_id"]
    cache_key = f"race_results:{race_id}"
    try:
        recorded = load_race_results(DATA_ROOT, base_url=feed_base_url, race_id=race_id)
        st.session_state[cache_key] = recorded
    except FeedError:
        recorded = st.session_state.get(cache_key)
        if recorded is None:
            st.info("Actual race results are not available yet.")
            return
        st.caption("Showing the last available race results while the feed is unavailable.")
    rows = sorted(recorded["results"], key=lambda row: row["position"])
    table, podium = "", ""
    for row in rows:
        code = _team_code(row.get("constructor_id"), row["constructor_name"])
        team_name, color = TEAMS[code]
        position = row["position"]
        table += (
            f'<div class="finish-row"><span class="position">{position}</span>'
            f'<span>{escape(row["driver_name"])}</span><span style="color:{color}">{escape(team_name)}</span>'
            f'<span class="points">{row["points"]:g}</span>'
            f'<span class="result-status">{escape(row["status"])}</span></div>'
        )
        if position <= 3:
            medal = MEDAL[position - 1]
            podium += (
                f'<div class="pchip"><span class="medal" style="background:{medal}">{position}</span>'
                f'<span class="who"><div class="nm">{escape(row["driver_name"])}</div>'
                f'<div class="tm"><span style="color:{color}">●</span> {escape(team_name)}</div></span>'
                f'<span class="prob">{row["points"]:g}<span style="font-size:12px"> pts</span></span></div>'
            )
    st.html(
        '<div class="results"><div class="card"><div class="panel-head"><h3>Actual Race Result</h3></div>'
        '<div class="finish-table"><div class="finish-row"><b>Pos</b><b>Driver</b><b>Team</b><b>Pts</b><b>Status</b></div>'
        f'{table}</div></div><div class="card"><div class="panel-head"><h3>Actual Podium</h3></div>'
        f'<div class="podium-body">{podium}</div></div></div>'
    )


inject_css()
st.html(header_html())


@st.fragment(run_every=60)
def prediction_dashboard() -> None:
    feed_base_url = _feed_base_url()
    feed_warning = None
    try:
        index = load_index(DATA_ROOT, base_url=feed_base_url)
        st.session_state["prediction_index"] = index
    except FeedError as exc:
        index = st.session_state.get("prediction_index")
        if not index:
            st.error(f"Prediction feed unavailable: {exc}")
            return
        feed_warning = "The latest feed check failed. Showing the last valid prediction."

    available = [entry["race_id"] for entry in index["races"]]
    selected = choose_race(
        index["active_race_id"], available,
        st.session_state.get("selected_race_id"),
        st.session_state.get("last_active_race_id"),
    )
    if st.session_state.get("selected_race_id") != selected:
        st.session_state["selected_race_id"] = selected
    st.session_state["last_active_race_id"] = index["active_race_id"]
    labels = {
        entry["race_id"]: f"{entry.get('race_name', entry['race_id'])} {entry.get('season', '')}".strip()
        for entry in index["races"]
    }

    with st.container(key="prediction_controls"):
        selector_col, status_col, _ = st.columns([2, 3, 3], vertical_alignment="bottom")
    with selector_col:
        race_id = st.selectbox(
            "Race prediction", available,
            format_func=lambda value: labels[value], key="selected_race_id",
        )

    cache_key = f"prediction_bundle:{race_id}"
    try:
        bundle = load_bundle(DATA_ROOT, base_url=feed_base_url, race_id=race_id, index=index)
        bundle = retain_latest_bundle(st.session_state.get(cache_key), bundle)
        st.session_state[cache_key] = bundle
    except FeedError as exc:
        bundle = st.session_state.get(cache_key)
        if bundle is None:
            st.error(f"Prediction unavailable: {exc}")
            return
        feed_warning = "The latest prediction was unavailable. Showing the last valid snapshot."

    historical = race_id != index["active_race_id"]
    if feed_warning:
        st.warning(feed_warning)
    view = "Prediction Result"
    if historical:
        view_col, _ = st.columns([2, 6])
        with view_col, st.container(key="archive_view_control"):
            view = st.selectbox(
                "View", ["Prediction Result", "Actual Race Result"], key=f"archive_view:{race_id}",
            )
    with status_col:
        if view == "Actual Race Result":
            st.html('<div class="control-status actual"><b>Actual Race Result.</b>'
                    '<span>Recorded finishing order, points and status.</span></div>')
        else:
            st.html(status_html(bundle.artifact, bundle.status, historical))
    if view == "Actual Race Result":
        _render_race_results(bundle.artifact, feed_base_url)
        return
    _render_dashboard(bundle.artifact)


prediction_dashboard()
