"""Saved-forecast presentation helpers; no data fetching or model imports."""
from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any, Mapping

import streamlit as st


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
TEAM_ID2CODE = {
    "mercedes": "MER",
    "ferrari": "FER",
    "mclaren": "MCL",
    "red_bull": "RBR",
    "aston_martin": "AST",
    "williams": "WIL",
    "alpine": "ALP",
    "rb": "RB",
    "racing_bulls": "RB",
    "alphatauri": "RB",
    "sauber": "SAU",
    "audi": "SAU",
    "kick_sauber": "SAU",
    "haas": "HAS",
    "cadillac": "CAD",
}
COUNTRY_FLAG = {
    "Australia": "🇦🇺",
    "China": "🇨🇳",
    "Japan": "🇯🇵",
    "USA": "🇺🇸",
    "United States": "🇺🇸",
    "Bahrain": "🇧🇭",
    "Saudi Arabia": "🇸🇦",
    "Spain": "🇪🇸",
    "Monaco": "🇲🇨",
    "Canada": "🇨🇦",
    "Austria": "🇦🇹",
    "UK": "🇬🇧",
    "United Kingdom": "🇬🇧",
    "Belgium": "🇧🇪",
    "Hungary": "🇭🇺",
    "Netherlands": "🇳🇱",
    "Italy": "🇮🇹",
    "Azerbaijan": "🇦🇿",
    "Singapore": "🇸🇬",
    "Mexico": "🇲🇽",
    "Brazil": "🇧🇷",
    "Qatar": "🇶🇦",
    "UAE": "🇦🇪",
    "United Arab Emirates": "🇦🇪",
}
MEDAL = {0: "#e9b949", 1: "#c8cdd3", 2: "#cd7f3e"}
BAR_STOPS = [
    "#ff3b30",
    "#ff5b42",
    "#ff7a3c",
    "#ff9a2e",
    "#ffb020",
    "#e8a93a",
    "#c79a4a",
    "#9c8a5c",
]


def _team_code(team_id, team_name):
    code = TEAM_ID2CODE.get(team_id) or (team_id or team_name or "UNK")[:3].upper()
    if code not in TEAMS:
        TEAMS[code] = (team_name or code, "#9aa0a6")
    return code


def _grid(rows, limit=12):
    return [
        (
            row.get("code") or row["driver_id"][:3].upper(),
            _team_code(row.get("teamId"), row.get("team")),
            None if row.get("gap") is None else float(row["gap"]),
            row.get("driverName") or row["driver_id"],
            row.get("position"),
        )
        for row in (rows or [])[:limit]
    ]


def _podium(rows, limit=8):
    return [
        (
            row.get("code") or row["driver_id"][:3].upper(),
            _team_code(row.get("teamId"), row.get("team")),
            int(round(float(row["podiumProbability"]) * 100)),
            row.get("driverName") or row["driver_id"],
        )
        for row in (rows or [])[:limit]
    ]


def prediction_to_race(event, prediction, status):
    forecast = prediction["forecast"]
    initial = status.get("initial_prediction") or prediction
    initial_forecast = initial.get("forecast", {})
    actual = prediction.get("mode") == "actual_qualifying"
    race_payload = forecast["race"]
    return {
        "round": int(event["round"]),
        "name": event.get("race_name") or race_payload.get("name") or "Grand Prix",
        "flag": COUNTRY_FLAG.get(event.get("country") or "", "🏁"),
        "quali": event.get("qualifying_start_at") or race_payload.get("qualifyingDate"),
        "race": event.get("race_start_at") or race_payload.get("date"),
        "pred": _grid(initial_forecast.get("predictedQualifying")),
        "podium": _podium(initial_forecast.get("preQualifyingPodium")),
        "real": _grid(forecast.get("realQualifying")) if actual else [],
        "podium_real": _podium(forecast.get("realGridPodium")) if actual else [],
    }


def _short(value: str) -> str:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.strftime("%a %m/%d")


def race_strip_html(race) -> str:
    return f"""
    <div class="race-strip">
      <span class="race-flag">{race['flag']}</span>
      <div class="race-name">
        <h2>{escape(str(race['name']))}</h2>
        <div class="race-meta">
          <span>Round <b>{race['round']:02d}</b></span>
          <span>Qualifying <b>{_short(race['quali'])}</b></span>
          <span>Race <b>{_short(race['race'])}</b></span>
        </div>
      </div>
    </div>
    """


def mode_html(actual: bool) -> str:
    if actual:
        label = "Actual qualifying available"
        sub = (
            "the race model uses official qualifying classification; grid penalties "
            "may still change the starting order."
        )
        cls = "real"
    else:
        label = "Pre-qualifying estimate"
        sub = "qualifying and podium are both ML estimates until validated session data arrives."
        cls = "pre"
    return (
        f'<div class="mode {cls}"><span class="pulse"></span><span>'
        f'<span class="label">{label}</span><span class="sub"> — {sub}</span>'
        "</span></div>"
    )


def quali_html(race, actual: bool) -> str:
    grid = race["real"] if actual else race["pred"]
    predicted = {row[0]: index for index, row in enumerate(race["pred"])}
    title = "Actual Qualifying" if actual else "Predicted Qualifying"
    hint = "official session · penalties excluded" if actual else "model · top 12"
    rows = []
    for index, (code, team, gap, name, official_position) in enumerate(grid):
        team_name, color = TEAMS[team]
        movement = ""
        if actual and code in predicted:
            delta = predicted[code] - index
            if delta:
                css = "up" if delta > 0 else "down"
                arrow = "▲" if delta > 0 else "▼"
                movement = f'<span class="delta {css}">{arrow}{abs(delta)}</span>'
        gap_text = "NO TIME" if gap is None else ("POLE" if gap == 0 else f"+{gap:.2f}")
        position = official_position if actual and official_position is not None else index + 1
        rows.append(
            f'<div class="qrow{" p1" if index == 0 else ""}">'
            f'<span class="pos">{position}</span><span class="drv">'
            f'<span class="teambar" style="background:{color}"></span>'
            f'<span class="code">{escape(str(code))}</span>'
            f'<span class="full">{escape(str(name))}</span>{movement}</span>'
            f'<span class="team">{escape(team_name)}</span>'
            f'<span class="gap{" zero" if gap == 0 else ""}">{gap_text}</span></div>'
        )
    return f"""
    <div class="card"><div class="panel-head"><span class="ic">🏎️</span>
      <h3>{title}</h3><span class="hint">{hint}</span></div>
      <div style="padding:8px 12px 14px;"><div class="qhead">
      <span style="text-align:center">P</span><span>Driver</span><span>Team</span>
      <span style="text-align:right">Gap</span></div>{''.join(rows)}</div></div>
    """


def podium_html(race, actual: bool) -> str:
    podium = race["podium_real"] if actual else race["podium"]
    if not podium:
        return '<div class="card"><div class="podium-body">Prediction temporarily unavailable</div></div>'
    chips = []
    for index, (code, team, probability, name) in enumerate(podium[:3]):
        team_name, color = TEAMS[team]
        chips.append(
            f'<div class="pchip"><span class="medal" style="background:{MEDAL[index]}">'
            f'{index + 1}</span><span class="who"><div class="nm">{escape(str(name))} '
            f'<span style="color:var(--muted);font-size:13px">{escape(str(code))}</span>'
            f'</div><div class="tm"><span style="color:{color}">●</span> '
            f'{escape(team_name)}</div></span><span class="prob">{probability}%</span></div>'
        )
    maximum = max(item[2] for item in podium) or 1
    bars = []
    for index, (code, _team, probability, _name) in enumerate(podium[:8]):
        color = BAR_STOPS[index] if index < len(BAR_STOPS) else "#7a766a"
        bars.append(
            f'<div class="brow"><span class="bl">{escape(str(code))}</span>'
            f'<span class="btrack"><span class="bfill" style="width:'
            f'{probability / maximum * 100:.1f}%;background:{color}"></span></span>'
            f'<span class="bv">{probability}%</span></div>'
        )
    return f"""
    <div class="card"><div class="panel-head"><span class="ic">🏆</span>
      <h3>Predicted Podium</h3><span class="hint">normalized top-3 estimate</span></div>
      <div class="podium-body">{''.join(chips)}<div class="bars">
      <div class="bt">Podium estimate · top 8</div>{''.join(bars)}</div></div></div>
    """


def compare_html(race) -> str:
    left = "".join(
        f'<div class="cmp-row"><span class="cp">{i + 1}</span>'
        f'<span><span class="cd">{escape(str(row[0]))}</span></span></div>'
        for i, row in enumerate(race["pred"][:8])
    )
    right = "".join(
        f'<div class="cmp-row"><span class="cp">{i + 1}</span>'
        f'<span><span class="cd">{escape(str(row[0]))}</span></span></div>'
        for i, row in enumerate(race["real"][:8])
    )
    return (
        '<div class="cmp-grid"><div class="cmp-col"><h5>Predicted pre-qualifying</h5>'
        f'{left}</div><div class="cmp-col"><h5>Actual qualifying</h5>{right}</div></div>'
    )


def _caption(status: Mapping[str, Any]) -> str:
    parts = []
    for field, label in (
        ("last_qualifying_check_started_at", "Last attempted"),
        ("last_successful_qualifying_check_at", "Last successful"),
        ("next_qualifying_check_at", "Next check"),
    ):
        if status.get(field):
            parts.append(f"{label}: {status[field]}")
    if status.get("validation_reason"):
        parts.append(f"Status: {status['validation_reason']}")
    if status.get("frozen_at"):
        parts.append(f"Frozen: {status['frozen_at']}")
    if status.get("reader_warning"):
        parts.append(f"Display note: {status['reader_warning']}")
    return " · ".join(parts)


def render_saved_prediction(event, prediction, status) -> None:
    """Render one confirmed saved selection or exact-event unavailability."""

    name = event.get("race_name") or f"Round {event.get('round', '?')}"
    if prediction is None:
        st.subheader(str(name))
        st.warning("Prediction temporarily unavailable")
        caption = _caption(status)
        if caption:
            st.caption(caption)
        return
    race = prediction_to_race(event, prediction, status)
    actual = prediction.get("mode") == "actual_qualifying"
    st.html(race_strip_html(race))
    st.html(mode_html(actual))
    st.caption(
        f"Saved forecast {prediction['prediction_id']} · generated "
        f"{prediction['generated_at']}"
    )
    caption = _caption(status)
    if caption:
        st.caption(caption)
    st.html(
        f'<div class="results">{quali_html(race, actual)}'
        f'{podium_html(race, actual)}</div>'
    )
    if actual and race["pred"]:
        with st.expander(
            "Compare: pre-qualifying vs actual qualifying", expanded=True
        ):
            st.html(compare_html(race))
