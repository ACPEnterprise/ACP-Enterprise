"""Canonical, secret-free test process configuration.

Pytest loads this file before test modules import the application.  Keeping the
environment selection here makes repository-root and absolute-path invocations
behave identically without a caller-managed ``PYTHONPATH`` or runtime secret
file.  Application test defaults are synthetic and delivery remains disabled.
"""

from __future__ import annotations

import os

os.environ.setdefault("ENVIRONMENT", "test")
