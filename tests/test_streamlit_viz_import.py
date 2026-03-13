from __future__ import annotations

import importlib


def test_streamlit_viz_module_imports_and_has_main() -> None:
    """
    Import scripts.streamlit_viz and ensure a main() function is defined.
    This is a light-weight check that avoids launching the UI.
    """
    mod = importlib.import_module("scripts.streamlit_viz")
    assert hasattr(mod, "main")

