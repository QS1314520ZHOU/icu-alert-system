from __future__ import annotations

import logging

from fastapi import APIRouter

from app import runtime

router = APIRouter()
logger = logging.getLogger("icu-alert")


@router.get("/api/knowledge/chunks/{chunk_id}")
async def get_knowledge_chunk(chunk_id: str):
    """离线知识库证据详情。"""
    try:
        bundle = runtime.ai_rag_service.get_chunk_bundle(chunk_id)
    except Exception as exc:
        logger.error("Knowledge chunk error: %s", exc)
        return {"code": 0, "chunk": {}, "error": f"知识库查询异常: {str(exc)[:120]}"}

    if not bundle:
        return {"code": 404, "message": "未找到知识片段"}
    return {"code": 0, "chunk": bundle}


@router.get("/api/knowledge/documents")
async def list_knowledge_documents():
    """列出本地离线知识包文档。"""
    try:
        docs = runtime.ai_rag_service.list_documents()
    except Exception as exc:
        logger.error("Knowledge documents error: %s", exc)
        return {"code": 0, "documents": [], "error": f"知识库查询异常: {str(exc)[:120]}"}
    return {"code": 0, "documents": docs}


@router.get("/api/knowledge/status")
async def get_knowledge_status():
    """离线知识包状态。"""
    try:
        status = runtime.ai_rag_service.status()
    except Exception as exc:
        logger.error("Knowledge status error: %s", exc)
        return {"code": 0, "status": {}, "error": f"知识库状态异常: {str(exc)[:120]}"}
    return {"code": 0, "status": status}


@router.get("/api/knowledge/documents/{doc_id}")
async def get_knowledge_document(doc_id: str):
    """获取本地离线知识文档及其章节。"""
    try:
        doc = runtime.ai_rag_service.get_document(doc_id, include_chunks=True)
    except Exception as exc:
        logger.error("Knowledge document detail error: %s", exc)
        return {"code": 0, "document": {}, "error": f"知识库查询异常: {str(exc)[:120]}"}
    if not doc:
        return {"code": 404, "message": "未找到知识文档"}
    return {"code": 0, "document": doc}


@router.post("/api/knowledge/reload")
async def reload_knowledge():
    """热更新离线知识包，无需重启服务。"""
    try:
        status = runtime.ai_rag_service.reload()
        if getattr(runtime.alert_engine, "_rag_service", None) is not None:
            runtime.alert_engine._rag_service = runtime.ai_rag_service
    except Exception as exc:
        logger.error("Knowledge reload error: %s", exc)
        return {"code": 0, "status": {}, "error": f"知识库热更新失败: {str(exc)[:120]}"}
    return {"code": 0, "status": status, "message": "知识库已热更新"}
