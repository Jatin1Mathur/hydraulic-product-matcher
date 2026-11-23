"""Smoke test: the Streamlit app runs, matches and answers without errors."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.db

APP = str(Path(__file__).resolve().parents[1] / "ui" / "app.py")


def test_streamlit_app(Session):  # noqa: N803 - fixture from test_integration
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    options = at.selectbox[0].options
    at.selectbox[0].select(next(o for o in options if "VT-D6" in o)).run()
    assert at.expander[0].label.startswith("1. OW-D6H")
    assert not at.exception
