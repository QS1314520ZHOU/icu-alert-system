from __future__ import annotations

import argparse
import sys
from typing import Any

import httpx


def _pretty_json(value: Any) -> str:
    import json

    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(value)


def _pick_patient(base_url: str, client: httpx.Client) -> str:
    resp = client.get(f"{base_url}/api/patients", timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    patients = payload.get("patients") if isinstance(payload, dict) else None
    if not isinstance(patients, list) or not patients:
        raise RuntimeError("未找到在院患者，无法执行冒烟验证。")
    patient_id = str((patients[0] or {}).get("_id") or "").strip()
    if not patient_id:
        raise RuntimeError("患者列表返回为空 ID。")
    return patient_id


def _pick_alert_patient(base_url: str, client: httpx.Client) -> str | None:
    try:
        resp = client.get(f"{base_url}/api/alerts/recent", params={"limit": 20}, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            return None
        for row in records:
            patient_id = str((row or {}).get("patient_id") or "").strip()
            if patient_id:
                return patient_id
    except Exception:
        return None
    return None


def _check_endpoint(base_url: str, client: httpx.Client, path: str, *, refresh: bool = True) -> dict[str, Any]:
    params = {"refresh": "true"} if refresh else None
    resp = client.get(f"{base_url}{path}", params=params, timeout=90)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} 返回非 JSON 对象。")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test for newly added ICU AI/scanner APIs.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--patient-id", default="", help="Optional patient id; if omitted, script picks the first patient")
    args = parser.parse_args()

    base_url = str(args.base_url or "").rstrip("/")
    if not base_url:
        print("base-url 不能为空", file=sys.stderr)
        return 2

    try:
        with httpx.Client() as client:
            default_patient_id = str(args.patient_id or "").strip() or _pick_patient(base_url, client)
            alert_patient_id = _pick_alert_patient(base_url, client) or default_patient_id
            print(f"[smoke] default_patient_id={default_patient_id}")
            print(f"[smoke] alert_patient_id={alert_patient_id}")

            checks = {
                "integrated_risk": (f"/api/ai/integrated-risk/{alert_patient_id}", alert_patient_id),
                "metabolic_phase": (f"/api/ai/metabolic-phase/{default_patient_id}", default_patient_id),
                "beta_blocker_advisor": (f"/api/ai/beta-blocker-advisor/{default_patient_id}", default_patient_id),
            }

            failures: list[str] = []
            for name, (path, pid) in checks.items():
                try:
                    payload = _check_endpoint(base_url, client, path, refresh=True)
                except Exception as exc:
                    failures.append(f"{name}: {exc}")
                    continue

                key = "report" if name == "integrated_risk" else "record"
                content = payload.get(key)
                error = payload.get("error")
                if error:
                    print(f"[warn] {name} returned error: {error}")
                print(f"[ok] {name} patient_id={pid}")
                if content is None:
                    print("[note] 当前样本患者未触发该模块或暂无可生成内容。")
                else:
                    print(_pretty_json(content)[:1600])
                print("-" * 60)

            if failures:
                print("[fail] 以下接口验证失败：", file=sys.stderr)
                for item in failures:
                    print(f"  - {item}", file=sys.stderr)
                return 1

            print("[pass] 新增 AI / scanner 接口全部可访问。")
            return 0
    except Exception as exc:
        print(f"[fail] 冒烟验证异常: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
