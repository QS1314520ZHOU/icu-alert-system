---
feature: ui-refactor-round2
status: in-progress
updated: 2026-08-27
branch: master
---

# ICU Alert System — Second Round UI/UX Refactor

## Report
(empty - not yet delivered)

## [S1] Problem
First-round refactor established design tokens and component extraction but left PatientDetail at 6,700+ lines with 3 overlapping navigation systems, AiConsult at 1,600 lines, residual dark/cyber CSS in ClinicalWorkflow, unreferenced design variables, and temporary debug scripts in the repository.

## [S2] Design

### S2.1 PatientDetail decomposition
- Single layout (`PatientDetailLayout.vue`) + 5 sub-views: Overview, Monitoring, Treatment, Decision, Documents
- Nested routes under `/patient/:id/:section`
- Backward-compatible query mapping from legacy `tab` param to new sections
- `usePatientDetail.ts` split into domain composables (identity, overview, monitoring, treatment, alerts, ai, documents)
- All child routes lazy-loaded

### S2.2 PatientOverviewView first screen
- Fixed patient header bar (bed, name, demographics, diagnosis, dept, safety strip)
- Single expanded top risk card; secondary risks collapsed
- Compact vital metric strip (6 values max)
- Shift tasks (3 max)
- Risk-correlated trend preview (2-3 traces)
- Evidence drawer for full detail

### S2.3 AiConsult decomposition
- Split into session list, header, message list, message item, composer, quick tasks, patient context, evidence panel, safety notice
- Extract stream parsing, export logic, session persistence, patient context adapter into separate composables/utils
- Target: AiConsult.vue ~500 lines

### S2.4 Design system unification
- Delete all CSS self-references (e.g., `--section-gap: var(--section-gap)`)
- All pages use design tokens from design-system.css
- Remove hardcoded colors (rgba cyber-cyan, neon effects)
- Replace inline badges/kpi-strips/page-tops with public design system components
- Ensure proper font stack: Noto Sans SC primary, Rajdhani only for monitor digits

### S2.5 SideNav convergence
- Max 6 primary items: 今日工作, 患者, 预警与任务, 交接班, AI助手, 更多
- "更多" opens overlay/drawer with grouped items (临床协作, 专项治疗, 管理分析, 科研, 系统管理)
- Mobile: bottom nav + more drawer

### S2.6 Repository hygiene
- Delete `_patch1.patch`, `backend/_check_db.py`, `backend/_check_patients.py`, `backend/_check_patients2.py`
- Add patterns to `.gitignore` and `.dockerignore`
- No real credentials or patient data in tracked files

### S2.7 Responsive compliance
- 1440, 1280, 1024, 390 widths tested
- No horizontal page scroll
- 390px: sidebar hidden, single column, panels become drawers

## [S3] Out of Scope
- Backend API changes
- New business features
- Database schema changes
- Authentication system changes
- Mobile native app changes (only mobile web responsive)

## Tasks
- [ ] T1: Delete temp files, fix CSS self-references, update gitignore/dockerignore — acceptance: temp files gone, no CSS self-ref, build passes (covers: S2.6, S2.4)
- [ ] T2: PatientDetail layout + nested routes + domain composables — acceptance: 5 sub-routes work, old query params mapped, PatientDetail.vue < 500 lines (covers: S2.1)
- [ ] T3: PatientOverviewView implementation — acceptance: header, risk card, vital strip, shift tasks, trend preview render correctly (covers: S2.2)
- [ ] T4: PatientMonitoring/Treatment/Decision/Document views — acceptance: each view renders its subsections, lazy loaded (covers: S2.1)
- [ ] T5: AiConsult decomposition — acceptance: AiConsult.vue < 600 lines, stream/export/session extracted (covers: S2.3)
- [ ] T6: Design system unification across NurseHome, ClinicalWorkflow, SideNav — acceptance: no hardcoded colors, public components used (covers: S2.4, S2.5)
- [ ] T7: Responsive + type-check + build verification — acceptance: vue-tsc passes, vite build passes, 4 viewport sizes OK (covers: S2.7)
