from app.alert_engine.clinical_commons import EntityResolver, convert_unit


class _Cfg:
    yaml_cfg = {
        "alert_engine": {
            "entity_resolver": {
                "drug_codes": {
                    "ABX001": {"is_antibiotic": True, "atc_class": "J01", "spectrum": "broad"},
                    "INS001": {"is_antibiotic": False, "atc_class": "A10A"},
                },
                "lab_item_codes": {
                    "BC001": {"test_key": "blood_culture", "loinc": "600-7"},
                },
            },
            "antibiotic_stewardship": {"antibiotic_keywords": ["meropenem"]},
        }
    }


def test_convert_unit_unknown_unit_is_excluded():
    assert convert_unit(36, "", "mmol/L", "glucose") == (None, "unknown")
    assert convert_unit(1.2, "", "umol/L", "creatinine") == (None, "unknown")


def test_entity_resolver_prefers_codes():
    resolver = EntityResolver(_Cfg())
    drug = resolver.resolve_drug({"drugCode": "ABX001", "drugName": "free text"})
    assert drug["match_method"] == "code"
    assert drug["is_antibiotic"] is True
    lab = resolver.resolve_lab_item({"itemCode": "BC001", "itemName": "other text"})
    assert lab["match_method"] == "code"
    assert lab["test_key"] == "blood_culture"


def test_entity_resolver_keyword_fallback_is_auditable():
    resolver = EntityResolver(_Cfg())
    drug = resolver.resolve_drug({"drugName": "meropenem"})
    assert drug["match_method"] == "keyword"
    assert drug["is_antibiotic"] is True
