from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(autouse=True)
def _isolate_shift_runtime_cache():
    """Isolate the global shift-config cache between every test.

    Clears ``runtime.shift_config`` and ``runtime.shift_config_loaded_at``
    before AND after each test so that:

    - No test can accidentally consume stale config from a previous test.
    - Tests that intentionally populate the cache do not leak to siblings.
    """
    from app import runtime

    runtime.shift_config = None
    runtime.shift_config_loaded_at = None
    yield
    runtime.shift_config = None
    runtime.shift_config_loaded_at = None
