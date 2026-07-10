# PatientNarrative / WhatIfConsole / ScannerMesh v1

## PatientNarrativeService

v1 uses rule-based structured generation only. It does not call LLMs and does not read `ai_*` collections, avoiding AI-output feedback loops. The source whitelist is vitals, labs, drugs, alerts, scanner outputs, workflow events, and assessments.

Each record in `patient_narratives` stores JSON and Markdown rendered from the same dataclass model. The unique key is `(patient_id, narrative_date)`. Dry run:

```yaml
patient_narrative:
  enabled: false
  max_context_chars: 6000
```

```bash
python -m app.services.patient_narrative_service --patient-id <id> --dry-run
```

Evolution path: v1 rules only; v2 may allow LLM to draft overview headlines after schema validation; v3 can tune rule weights from clinician edits.

## WhatIfConsole

The digital twin tab exposes a right-side console for single-intervention what-if simulation. It reuses `POST /api/ai/what-if/{patient_id}` and logs queries to `whatif_query_log`. v1 is view-only and does not create orders or write to the medical record.

## ScannerMesh

v1 is an in-process asyncio sidecar bus with frozen `DerivedFact` objects. It never injects facts back into scanners and does not write MongoDB. It is guarded by:

```yaml
scanner_mesh:
  enabled: false
  publish_only: false
  max_facts_per_patient: 500
  fact_ttl_seconds: 1800
```

Dry run:

```bash
python -m app.alert_engine.scanner_mesh --patient-id <id> --dry-run
```

This PR deliberately does not publish from existing scanners yet. Later PRs can add low-risk subscribers/publishers after reviewing scanner-specific event contracts.
