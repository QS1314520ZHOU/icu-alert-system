# ICU Alert Engine Clinical Logic Migration

## Scope

This migration changes only the five core alert areas requested: Sepsis, AKI, cardiac arrest risk calibration support, VTE prophylaxis, and glycemic control.

## Clinical Logic Changes

### Shared clinical commons

- Added `backend/app/alert_engine/clinical_commons.py`.
- Centralized date parsing, numeric parsing, strict unit conversion, urine output rate calculation, and code-first entity resolution.
- Drug/lab recognition now records `match_method` where the module uses `EntityResolver`.

### AKI

- KDIGO staging now uses both creatinine and urine-output tracks and takes the higher stage.
- Creatinine values with unknown units are excluded from staging instead of guessed.
- AKI output includes `creatinine_stage`, `urine_stage`, `trigger_paths`, `trigger_source`, and `data_completeness`.

Historical comparability impact: AKI alerts may decrease where creatinine units are missing, and may increase where urine output meets KDIGO criteria.

### Sepsis Hour-1 Bundle

- Bundle quality now separates `completion_ratio` from `on_time_ratio`.
- Hour-1 compliance uses on-time completion only.
- Blood culture before antibiotic is `None` when antibiotic timing is missing, rather than defaulting to `True`.
- Blood culture matching can use configured item codes before keyword fallback.

Historical comparability impact: previous bundle completion rates may have overstated on-time compliance.

### Cardiac Arrest Risk

- Runtime feature logic is preserved.
- Added `backend/scripts/calibrate_cardiac_arrest.py` to report PPV, observed sensitivity, observed miss rate, and alerts/day across threshold grids.
- The script does not change production thresholds automatically.

Historical comparability impact: none at runtime until thresholds are manually changed after review.

### VTE Prophylaxis

- Pharmacologic and mechanical prophylaxis can use configured order/drug codes before keyword fallback.
- Passive activity such as turning or passive ROM no longer counts as ambulation.
- Padua/Caprini risk assessment is marked unassessable when key input data are missing, avoiding false low-risk conclusions.

Historical comparability impact: VTE omission alerts may increase for immobile patients previously counted as active due to passive-care notes.

### Glycemic Control

- Unknown glucose units are excluded from critical-value decisions.
- This removes the unsafe fallback that could convert a true 36 mmol/L hyperglycemic crisis into 2.0 mmol/L.
- Default low critical threshold is now 2.8 mmol/L and high critical threshold is 22.2 mmol/L; defaults require ICU physician review before production use.
- Low glucose alerts take precedence over high-glucose workflow checks.

Historical comparability impact: glucose alerts may decrease where units are absent; severe hypoglycemia counts may change due to the 2.8 mmol/L default.

## Maturity Metadata

- `ScannerSpec` now includes `maturity`, defaulting to `experimental`.
- The five core scanners are marked `validated`.
- Other scanners are experimental by default in scanner telemetry.

## Red-Flag Logic Changes Requiring Clinical Review

- AKI: unknown creatinine units no longer contribute to staging.
- AKI: urine-output KDIGO staging can independently raise AKI stage.
- Sepsis: late bundle completion no longer counts as Hour-1 compliant.
- Glycemic control: unknown glucose units no longer produce hypo/hyperglycemia critical alerts.
- Glycemic control: default severe hypoglycemia threshold changed to 2.8 mmol/L pending ICU physician confirmation.
- VTE: passive movement notes no longer count as patient mobilization.

## Example Cardiac Arrest Calibration Report

Run:

```bash
python backend/scripts/calibrate_cardiac_arrest.py --days 30 --output cardiac_arrest_calibration.json
```

Report shape:

```json
{
  "module": "cardiac_arrest_risk",
  "generated_at": "2026-06-26T10:00:00",
  "window_days": 30,
  "default_thresholds": {"warning_score": 4, "high_score": 6, "critical_score": 8},
  "rows": [
    {
      "warning_score": 4,
      "high_score": 6,
      "critical_score": 8,
      "alerts": 12,
      "true_positives": 3,
      "ppv": 0.25,
      "sensitivity_observed_alert_space": 0.75,
      "miss_rate_observed_alert_space": 0.25,
      "alerts_per_day": 0.4
    }
  ]
}
```
