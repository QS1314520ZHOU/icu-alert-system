# ICU Research Topic Placement

## Online Real-Time

- Respiratory deterioration forecast
  - Menu placement: Respiratory Dashboard, inside the patient drawer as "呼吸恶化预警".
  - Frontend: `frontend/src/views/RespiratoryTherapistDashboard.vue`, `frontend/src/api/respiratory.ts`.
  - Backend: `backend/app/alert_engine/respiratory_deterioration_predictor.py`, `scanner_respiratory_deterioration.py`, `/api/respiratory/{patient_id}/deterioration-forecast`.
  - Reused capabilities: ventilator binding, `deviceCap`, `bedside`, field mapping, `score`, alert broadcast.
  - Metadata: `maturity: "experimental"`, `feature_schema_version`, `data_source`, `validation_status`.

- MDRO high-risk screening trigger
  - Menu placement: Rule Health / alert-engine operations, infection-control panel.
  - Frontend: `frontend/src/views/ScannerHealth.vue`.
  - Backend: `backend/app/alert_engine/microbiology_monitor.py`, `scanner_microbiology.py`.
  - Reused capabilities: MDRO typing, susceptibility parsing, coverage mismatch checks, `alert_records`, WebSocket/Pulse candidate flow.
  - Metadata: `maturity: "experimental"`, `feature_schema_version`, `data_source`, `validation_status`.

## Offline Research

- Respiratory forecast model
  - Menu placement: Research Workbench internal tab "呼吸预警模型".
  - Frontend/API: `ResearchWorkbench.vue`, `/api/research/respiratory-forecast/status`.
  - Scripts: `backend/scripts/research/respiratory_forecast/`.
  - Shared feature builder: `backend/app/alert_engine/features/respiratory_features.py`.

- MDRO control analysis
  - Menu placement: Research Workbench internal tab "MDRO 防控分析".
  - Frontend/API: `ResearchWorkbench.vue`, `/api/research/mdro-control/summary`.
  - Scripts: `backend/scripts/research/mdro_control/`.
  - Shared feature builder: `backend/app/alert_engine/features/mdro_features.py`.
  - WGS: placeholder only; requires external microbiology data and is not implemented in this phase.

## Data Adapters

- Online/internal source: `backend/app/data_adapters/mongo_adapter.py`.
- External validation placeholder: `backend/app/data_adapters/eicu_adapter.py`.
- Standard observation contract: `concept`, `value`, `unit`, `timestamp`, `source`, `match_method`.
