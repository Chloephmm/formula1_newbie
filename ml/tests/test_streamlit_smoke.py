"""Streamlit viewer smoke test."""
from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_loads_published_feed_without_a_run_button():
    app = Path(__file__).parents[2] / "streamlit_app" / "app.py"

    result = AppTest.from_file(str(app)).run(timeout=20)

    assert list(result.exception) == []
    assert [widget.value for widget in result.selectbox] == ["2026-19"]
    assert list(result.button) == []


def test_archived_race_switches_views_without_changing_forecast():
    app = Path(__file__).parents[2] / "streamlit_app" / "app.py"
    artifact = app.parents[1] / "web/public/data/predictions/2026-18.json"
    original = artifact.read_bytes()
    result = AppTest.from_file(str(app)).run(timeout=20)
    assert len(result.selectbox) == 1
    result.selectbox[0].select("2026-18").run()
    assert not list(result.exception)
    assert result.selectbox[1].value == "Prediction Result"
    result.selectbox[1].select("Actual Race Result").run()
    assert not list(result.exception)
    html = " ".join(element.proto.body for element in result.get("html"))
    assert "Actual Podium" in html
    assert "Andrea Kimi Antonelli" in html
    assert "Predicted Podium" not in html
    result.run()
    assert result.selectbox[1].value == "Actual Race Result"
    result.selectbox[1].select("Prediction Result").run()
    assert not list(result.exception)
    assert artifact.read_bytes() == original
    result.selectbox[0].select("2026-19").run()
    assert len(result.selectbox) == 1
