"""Thin entrypoint that preserves the historic `app` import path."""

from __future__ import annotations

import importlib
import sys


_web_app_module = importlib.import_module("trh.web.app")


if __name__ == "__main__":
    _web_app_module.main()
else:
    sys.modules[__name__] = _web_app_module
