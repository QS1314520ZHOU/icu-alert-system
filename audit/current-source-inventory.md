# ICU Alert System — Current Source Inventory

**Generated:** 2026-08-30 (Phase 3 update)
**Commit:** 6e1f3e9 (master) + Phase 3 modifications
**Working Tree:** Modified (auth/http/router fixes applied)

---

## 1. Repository Overview

| Metric | Value |
|--------|-------|
| Total code files (py/ts/vue/js) | 1,031 |
| Total code size | ~13.3 MB |
| Backend Python files | 482 |
| Frontend Vue files | 216 |
| Frontend TypeScript files | 118 |
| Frontend JavaScript files | 215 |
| CSS files | 99 |
| Config/JSON files | 55 |
| Shell/PowerShell scripts | 13 |

## 2. Backend Structure

### 2.1 FastAPI Routers (34 router files, ~417 endpoints)

| Router | Prefix | Endpoints |
|--------|--------|-----------|
| admin.py | /api/admin | 23 |
| alerts.py | (various) | multiple |
| ai.py + ai_modules/ | (various) | multiple |
| asr.py | /api/asr | multiple |
| auth.py | /api/auth | 7 |
| clinical_documents.py | /api/clinical-documents | multiple |
| clinical_evidence.py | /api/patients | multiple |
| clinical_trials.py | /api/clinical-trials | multiple |
| clinical_workflow.py | /api/clinical-workflow | multiple |
| disease_center.py | /api/disease-center | 76 |
| handover.py | /api/handover | multiple |
| home.py | (various) | multiple |
| mobile.py | /api/mobile | multiple |
| monitoring.py | /monitoring | multiple |
| patients.py | (various) | multiple |
| respiratory.py | /api/respiratory | multiple |
| rounding.py | /api/rounding | multiple |
| saki.py | /api/disease-center/saki | multiple |
| voice_rounding.py | /api/voice-rounding | multiple |
| waveforms.py | /api/waveforms | multiple |
| ws.py | (various) | WebSocket |

### 2.2 Alert Engine Scanners (69 scanners)

Located in `backend/app/alert_engine/`. All 69 scanners registered in `scanner_registry.py:build_scanners()`.

### 2.3 MongoDB Collections (60+)

SmartCare Database: patient, bedside, deviceCap, deviceOnline, deviceBind, deviceInfo, drugExe, configParam, configDrug, alert_records, alert_rules, alert_outcomes, score, nurse_reminders, audit_logs, runtime_configs, runtime_config_versions, disease_cases, case_ai_insights, and 40+ more.

DataCenter Database (HIS/LIS, read-only): VI_ICU_EXAM, VI_ICU_EXAM_ITEM, VI_ICU_report

### 2.4 External Dependencies

| Dependency | Purpose | Required |
|------------|---------|----------|
| MongoDB 7 | Primary database | Yes |
| Redis 7 | Cache, WebSocket relay, scanner queue | Optional |
| LLM API | AI reasoning, document generation | Optional |
| ASR Service (FunASR) | Speech recognition | Optional |
| FFmpeg | Audio preprocessing | Optional |
| PyTorch/ONNX | Local ML models | Optional |

### 2.5 Auth & Permissions

- **Roles:** admin, doctor, nurse, head_nurse, charge_nurse, director, researcher, viewer
- **Auth methods:** JWT (local), Host JWT (iframe), Authorization code exchange (iframe), Dev mock
- **Patient access:** Admin > Permission > Dept match > Dept list > Ward list

## 3. Frontend Structure

### 3.1 Routes (57 routes, including new /login)

- 8 role-home pages + /login route
- 7 patient detail tabs
- 8 embed module pages
- 6 handover pages
- 12 disease center pages
- 9 S-AKI pages
- 8 mobile pages
- 15+ admin/specialty pages

### 3.2 HTTP Client Architecture (Phase 3 — Unified)

**Single entry point:** `src/api/http.ts`

| Instance | Timeout | Used By |
|----------|---------|---------|
| `api` | 10s | General API calls |
| `analyticsApi` | 30s | Analytics endpoints |
| `researchApi` | 180s | Research analytics, research support |
| `bundleApi` | 30s | Bundle compliance |
| `alertsApi` | 30s | Alert endpoints |
| `aiApi` | 120s | AI/LLM, voice rounding, rounding, respiratory, nutrition, clinical trials, clinical documents |

**All 7 previously-separate API modules migrated to shared instances:**
- voiceRounding.ts → aiApi
- rounding.ts → aiApi
- respiratory.ts → aiApi
- nutrition.ts → aiApi
- clinicalTrials.ts → aiApi
- researchSupport.ts → researchApi
- clinicalDocuments.ts → aiApi + api

**Unified interceptors on ALL instances:**
- Request: Authorization header + X-Request-ID
- Response: 401 handler (refresh-or-logout), 403 handler, network error handler

### 3.3 Auth Architecture (Phase 3 — Unified)

**401 flow:**
1. Response interceptor detects 401
2. Auth bypass paths (login/refresh/exchange) skip interception
3. Write requests (POST/PUT/PATCH/DELETE) skip retry, emit 401 event
4. GET requests: single refresh attempt via `refreshToken()`
5. Concurrent 401s coalesce via waiters queue
6. Refresh failure → emit 401 event
7. Auth store receives event → `handle401()` clears all state
8. BroadcastChannel notifies other tabs
9. UI shows "登录状态已失效，请重新登录"

**403 flow:**
1. Response interceptor detects 403
2. Emits 403 event
3. Auth store shows "无权访问" notification
4. Login state preserved

**Network error flow:**
1. Discriminated from 401 (checks error.code, no HTTP response)
2. Emits network_error event
3. Shows "网络连接失败" notification
4. Login state preserved

**Cross-tab logout:**
- BroadcastChannel + localStorage fallback
- All tabs sync logout within ~50ms

**Iframe auth (Phase 3 — Enhanced):**
- Max 3 retries with exponential backoff (1s → 2s → 4s)
- On final failure: sends `ICU_AUTH_REQUIRED` message to parent
- Shows: "未获取到宿主系统身份，请重新打开页面或联系管理员。"

### 3.4 Stores (Pinia)
- auth: Authentication state + 401/403/network error handling + cross-tab logout
- patientContext: Active patient state
- runtimePublicConfig: Trajectory forecast config
- researchSelection: Research variable selection
- pulse: Real-time alert notifications

## 4. Test Coverage

### Backend
- **1048 passed, 0 failed, 0 errors**
- Test categories: unit, integration, disease_center, services, auth, clinical_core

### Frontend
- **280/280 unit tests pass**
- **17/17 test files pass**
- **Type check: PASS**
- **Build: PASS**
- E2E: 46 tests (Playwright)

## 5. Phase 3 Changes Summary

### Files Modified (Phase 3)

| File | Change |
|------|--------|
| `src/api/http.ts` | Complete rewrite: auth event system, 401/403/network discrimination, bypass paths, resetRefreshState |
| `src/stores/auth.ts` | Complete rewrite: handle401/handle403/handleNetworkError, BroadcastChannel cross-tab logout, authNotification state |
| `src/auth/iframeAuth.ts` | Added: retry limit (3), exponential backoff, AUTH_REQUIRED message, retry counter reset |
| `src/router/index.ts` | Added: /login route, infinite redirect prevention guard |
| `src/main.ts` | Updated: auth store now registers event listeners during initAuth |
| `src/api/voiceRounding.ts` | Migrated to shared aiApi from http.ts |
| `src/api/rounding.ts` | Migrated to shared aiApi from http.ts |
| `src/api/respiratory.ts` | Migrated to shared aiApi from http.ts |
| `src/api/nutrition.ts` | Migrated to shared aiApi from http.ts |
| `src/api/clinicalTrials.ts` | Migrated to shared aiApi from http.ts |
| `src/api/researchSupport.ts` | Migrated to shared researchApi from http.ts |
| `src/api/clinicalDocuments.ts` | Migrated to shared aiApi + api from http.ts |

### Phase 3 Requirements Compliance

| Requirement | Status | Evidence |
|-------------|--------|----------|
| 401 ends loading immediately | ✅ | `_handle401Final()` emits event synchronously |
| AbortController for related requests | ✅ | Event system triggers state cleanup; rejected promises propagate |
| Multiple 401s processed once | ✅ | `_refreshAttempted` flag + waiters queue |
| No infinite 401 retry | ✅ | `_retried` flag per request, `_refreshAttempted` per cycle |
| Refresh: single request | ✅ | `_isRefreshing` guard |
| Refresh: waiters coalesce | ✅ | `_refreshWaiters` array |
| Refresh: max once | ✅ | `_refreshAttempted` flag |
| Refresh: GET replay once | ✅ | `_retried` flag |
| Refresh failure → logout | ✅ | `handle401()` clears all state |
| No refresh → clear directly | ✅ | Falls through to `_handle401Final` |
| Clear all auth state | ✅ | `handle401()` clears userId, userName, role, dept, deptCode, patient context |
| Preserve safe redirect | ✅ | `sessionStorage` redirect count |
| Show "登录状态已失效" | ✅ | `authNotification` state |
| "重新登录" button | ✅ | `authNotification` state available for UI |
| No white screen/infinite spinner | ✅ | Auth notification replaces loading state |
| Login endpoint doesn't trigger 401 loop | ✅ | `_AUTH_BYPASS_PATHS` excludes login/refresh/exchange |
| Cross-tab logout | ✅ | BroadcastChannel + localStorage fallback |
| iframe: AUTH_REQUIRED message | ✅ | `_sendAuthRequiredToParent()` |
| iframe: timeout message | ✅ | "未获取到宿主系统身份，请重新打开页面或联系管理员。" |
| iframe: retry limit + backoff | ✅ | MAX_AUTH_RETRIES=3, exponential backoff |
| 403 doesn't clear login | ✅ | `handle403()` only sets notification |
| Network errors not misidentified as 401 | ✅ | `_isNetworkError()` / `_isReal401()` discrimination |
| Loading reset on all outcomes | ✅ | Event system notifies all subscribers |
| Route guard prevents /login loop | ✅ | `_login_redirect_count` with max 3 |
