from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from typing import Any, AsyncIterator

from app.services.agent_tools import AutonomousAgentTools
from app.services.llm_runtime import call_llm_chat


class AutonomousInvestigationAgent:
    def __init__(self, *, db, config, alert_engine, rag_service=None, max_rounds: int = 8, timeout_seconds: int = 90) -> None:
        self.db = db
        self.config = config
        self.alert_engine = alert_engine
        self.tools = AutonomousAgentTools(db=db, config=config, alert_engine=alert_engine, rag_service=rag_service)
        self.max_rounds = max(1, min(int(max_rounds or 8), 8))
        self.timeout_seconds = max(10, min(int(timeout_seconds or 90), 90))

    def _plan(self, patient_id: str, question: str) -> list[tuple[str, dict[str, Any]]]:
        query = str(question or "ICU 自主排查")
        return [
            ("get_digital_twin", {"patient_id": patient_id}),
            ("run_scanner_summary", {"patient_id": patient_id}),
            ("query_knowledge_graph", {"patient_id": patient_id, "abnormal_finding": query[:80]}),
            ("rag_search", {"query": query}),
        ][: self.max_rounds]

    async def _synthesize(self, *, question: str, tool_results: list[dict[str, Any]]) -> str:
        system = "你是ICU自主排查Agent。基于工具证据生成简洁结论，列出证据、主要风险、下一步核对点。不得生成正式医嘱。"
        user = json.dumps({"question": question, "tool_results": tool_results}, ensure_ascii=False, default=str)
        try:
            result = await call_llm_chat(cfg=self.config, system_prompt=system, user_prompt=user, model=self.config.llm_fast_model or self.config.llm_model_medical, temperature=0.1, max_tokens=1200, timeout_seconds=30)
            text = str(result.get("text") or "").strip()
            if text:
                return text
        except Exception:
            pass
        summaries = []
        for row in tool_results:
            summaries.append(f"{row.get('tool')}: {str(row.get('result'))[:180]}")
        return "自主排查完成。证据摘要：\n" + "\n".join(f"{idx}、{item}" for idx, item in enumerate(summaries, start=1)) + "\n建议由责任医生结合床旁情况复核上述风险点。"

    async def investigate(self, *, patient_id: str, question: str) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        started = time.monotonic()
        failures = 0
        cache_hits: Counter[str] = Counter()
        results: list[dict[str, Any]] = []
        for idx, (tool_name, args) in enumerate(self._plan(patient_id, question), start=1):
            if time.monotonic() - started > self.timeout_seconds:
                yield "error", {"message": "自主排查超过90秒上限，已停止。"}
                break
            cache_key = f"{tool_name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
            cache_hits[cache_key] += 1
            if cache_hits[cache_key] >= 2:
                yield "step", {"round": idx, "tool": tool_name, "status": "stopped_by_cache", "reason": "同工具同参数命中2次缓存即停"}
                break
            yield "step", {"round": idx, "tool": tool_name, "arguments": args}
            try:
                result = await asyncio.wait_for(self.tools.call(tool_name, args), timeout=max(5, self.timeout_seconds - int(time.monotonic() - started)))
                row = {"tool": tool_name, "arguments": args, "result": result}
                results.append(row)
                yield "tool_result", row
                if isinstance(result, dict) and result.get("available") is False:
                    failures += 1
            except Exception as exc:
                failures += 1
                yield "tool_result", {"tool": tool_name, "arguments": args, "error": str(exc)[:180]}
            if failures >= 3:
                yield "error", {"message": "累计3次工具失败，已结束自主排查。"}
                break
        final = await self._synthesize(question=question, tool_results=results)
        yield "final", {"answer": final, "tool_count": len(results), "elapsed_seconds": round(time.monotonic() - started, 2)}
