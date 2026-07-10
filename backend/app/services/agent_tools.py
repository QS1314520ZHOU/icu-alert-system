from __future__ import annotations

from typing import Any

from bson import ObjectId

from app.services.clinical_knowledge_graph import ClinicalKnowledgeGraph
from app.services.patient_digital_twin import PatientDigitalTwinService
from app.services.patient_narrative_service import PatientNarrativeService


def autonomous_tool_schemas() -> list[dict[str, Any]]:
    return [
        {"type": "function", "function": {"name": "get_digital_twin", "description": "获取患者数字孪生快照", "parameters": {"type": "object", "properties": {"patient_id": {"type": "string"}}, "required": ["patient_id"]}}},
        {"type": "function", "function": {"name": "run_scanner_summary", "description": "汇总近24小时scanner高危信号", "parameters": {"type": "object", "properties": {"patient_id": {"type": "string"}}, "required": ["patient_id"]}}},
        {"type": "function", "function": {"name": "query_knowledge_graph", "description": "查询临床知识图谱因果推理", "parameters": {"type": "object", "properties": {"patient_id": {"type": "string"}, "abnormal_finding": {"type": "string"}}, "required": ["patient_id"]}}},
        {"type": "function", "function": {"name": "rag_search", "description": "检索本地指南/RAG证据", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    ]


class AutonomousAgentTools:
    def __init__(self, *, db, config, alert_engine, rag_service=None) -> None:
        self.db = db
        self.config = config
        self.alert_engine = alert_engine
        self.rag_service = rag_service

    async def get_digital_twin(self, patient_id: str) -> dict[str, Any]:
        try:
            patient = await self.db.col("patient").find_one({"_id": ObjectId(patient_id)})
        except Exception:
            patient = await self.db.col("patient").find_one({"_id": patient_id})
        if not patient:
            return {"available": False, "reason": "patient not found"}
        service = PatientDigitalTwinService(db=self.db, config=self.config, alert_engine=self.alert_engine)
        snapshot = await service.get_or_build_snapshot(str(patient.get("_id") or patient_id), patient, hours=24, refresh=False, persist=True)
        narrative_context = ""
        try:
            narrative_context = await PatientNarrativeService(db=self.db, config=self.config, alert_engine=self.alert_engine).latest_context_text(str(patient.get("_id") or patient_id), days=7, max_chars=4000)
        except Exception:
            narrative_context = ""
        return {"available": True, "summary": snapshot.get("summary"), "problem_list": snapshot.get("problem_list"), "foundation_model_predictions": snapshot.get("foundation_model_predictions"), "narrative_context": narrative_context}

    async def run_scanner_summary(self, patient_id: str) -> dict[str, Any]:
        cursor = self.db.col("alert_records").find({"patient_id": str(patient_id), "is_active": True}).sort("created_at", -1).limit(20)
        rows = [doc async for doc in cursor]
        return {"count": len(rows), "alerts": [{"rule_id": row.get("rule_id"), "name": row.get("name"), "severity": row.get("severity"), "alert_type": row.get("alert_type")} for row in rows[:10]]}

    async def query_knowledge_graph(self, patient_id: str, abnormal_finding: str = "") -> dict[str, Any]:
        graph = ClinicalKnowledgeGraph(db=self.db, config=self.config, alert_engine=self.alert_engine, rag_service=self.rag_service)
        if hasattr(graph, "analyze_abnormal_finding"):
            return await graph.analyze_abnormal_finding(patient_id, abnormal_finding or "综合风险")
        return {"available": False, "reason": "knowledge graph query method unavailable"}

    async def rag_search(self, query: str) -> dict[str, Any]:
        if not self.rag_service:
            return {"available": False, "reason": "rag not configured"}
        try:
            if hasattr(self.rag_service, "search"):
                rows = await self.rag_service.search(query=query, top_k=4)
            else:
                rows = await self.rag_service.retrieve(query, top_k=4)
            return {"available": True, "items": rows[:4] if isinstance(rows, list) else []}
        except Exception as exc:
            return {"available": False, "reason": str(exc)[:160]}

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "get_digital_twin":
            return await self.get_digital_twin(str(arguments.get("patient_id") or ""))
        if name == "run_scanner_summary":
            return await self.run_scanner_summary(str(arguments.get("patient_id") or ""))
        if name == "query_knowledge_graph":
            return await self.query_knowledge_graph(str(arguments.get("patient_id") or ""), str(arguments.get("abnormal_finding") or ""))
        if name == "rag_search":
            return await self.rag_search(str(arguments.get("query") or ""))
        return {"available": False, "reason": f"unknown tool: {name}"}
