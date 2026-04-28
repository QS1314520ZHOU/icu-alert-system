from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.omop_export_service import MAPPING_CONFIG, OMOP_TABLES


def test_omop_minimum_tables_have_mapping_framework() -> None:
    assert "PERSON" in OMOP_TABLES
    assert "MEASUREMENT" in OMOP_TABLES
    assert set(OMOP_TABLES).issubset(set(MAPPING_CONFIG.keys()))
