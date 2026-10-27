"""Minimal AppTest harness for the saved-feed reader and timed fragment."""
from __future__ import annotations

import os

import streamlit as st

from streamlit_app.prediction_data import read_saved_event
from streamlit_app.prediction_view import render_saved_prediction


@st.fragment(run_every="60s")
def forecast_panel(event_id: str):
    event, prediction, status = read_saved_event(
        event_id,
        disk_path=os.environ.get("PREDICTION_FEED_FILE"),
    )
    render_saved_prediction(event, prediction, status)


forecast_panel(os.environ.get("PREDICTION_EVENT_ID", "2026-1"))
