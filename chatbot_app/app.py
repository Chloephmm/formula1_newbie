"""Standalone, embeddable chat: only reads the repository's existing outputs."""
from pathlib import Path

import streamlit as st
from f1buddy_ai import render_chatbot_panel

st.set_page_config(page_title="F1 Buddy", page_icon="🏁", layout="centered")
st.title("F1 Buddy")
render_chatbot_panel(data_dir=Path(__file__).resolve().parents[1] / "web" / "public" / "data")
