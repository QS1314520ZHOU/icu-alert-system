"""
病种中心路由
代理规则核心 API，提供术语编码、评分规则等功能
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.rule_core_client import get_rule_core_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/disease-center", tags=["disease-center"])


# ---- 健康检查 ----

@router.get("/health")
async def health_check():
    """检查规则核心连接状态"""
    client = get_rule_core_client()
    result = await client.health_check()
    return {"rule_core": result}


# ---- 评分系统 ----

@router.get("/scoring/systems")
async def list_scoring_systems():
    """获取所有评分系统列表"""
    try:
        client = get_rule_core_client()
        systems = await client.list_scoring_systems()
        return {"systems": systems}
    except Exception as e:
        logger.error("获取评分系统列表失败: %s", e)
        raise HTTPException(status_code=502, detail=f"规则核心服务不可用: {e}")


@router.get("/scoring/rules/{rule_id}")
async def get_scoring_rule(rule_id: str):
    """获取评分规则详情"""
    try:
        client = get_rule_core_client()
        rule = await client.get_scoring_rule(rule_id)
        return rule
    except Exception as e:
        logger.error("获取评分规则失败: %s -> %s", rule_id, e)
        raise HTTPException(status_code=502, detail=f"规则核心服务不可用: {e}")


@router.post("/scoring/evaluate")
async def evaluate_score(payload: dict[str, Any]):
    """执行评分计算"""
    try:
        client = get_rule_core_client()
        result = await client.evaluate_score(
            patient_id=payload.get("patient_id", ""),
            score_system=payload.get("score_system", ""),
            score_variant=payload.get("score_variant"),
            inputs=payload.get("inputs"),
        )
        return result
    except Exception as e:
        logger.error("评分计算失败: %s", e)
        raise HTTPException(status_code=502, detail=f"规则核心服务不可用: {e}")


@router.post("/scoring/test-case")
async def run_test_case(payload: dict[str, Any]):
    """执行测试病例"""
    try:
        client = get_rule_core_client()
        result = await client.run_test_case(
            rule_id=payload.get("rule_id", ""),
            test_case=payload.get("test_case", {}),
        )
        return result
    except Exception as e:
        logger.error("测试病例执行失败: %s", e)
        raise HTTPException(status_code=502, detail=f"规则核心服务不可用: {e}")


# ---- 术语编码 ----

@router.get("/terminology/search")
async def search_terminology(
    q: str = Query(..., description="搜索关键词"),
    category: Optional[str] = Query(None, description="分类过滤"),
    limit: int = Query(20, ge=1, le=100),
):
    """搜索术语"""
    try:
        client = get_rule_core_client()
        items = await client.search_terminology(q, category=category, limit=limit)
        return {"items": items}
    except Exception as e:
        logger.error("术语搜索失败: %s", e)
        raise HTTPException(status_code=502, detail=f"规则核心服务不可用: {e}")


@router.get("/terminology/categories")
async def list_terminology_categories():
    """获取术语分类列表"""
    try:
        client = get_rule_core_client()
        categories = await client.list_terminology_categories()
        return {"categories": categories}
    except Exception as e:
        logger.error("获取术语分类失败: %s", e)
        raise HTTPException(status_code=502, detail=f"规则核心服务不可用: {e}")


@router.get("/terminology/{term_id}")
async def get_terminology_detail(term_id: str):
    """获取术语详情"""
    try:
        client = get_rule_core_client()
        detail = await client.get_terminology_detail(term_id)
        return detail
    except Exception as e:
        logger.error("获取术语详情失败: %s -> %s", term_id, e)
        raise HTTPException(status_code=502, detail=f"规则核心服务不可用: {e}")


# ---- 病种 ----

@router.get("/diseases")
async def list_diseases(
    category: Optional[str] = Query(None, description="分类过滤"),
    status: Optional[str] = Query(None, description="状态过滤"),
    limit: int = Query(50, ge=1, le=200),
):
    """获取病种列表"""
    try:
        client = get_rule_core_client()
        diseases = await client.list_diseases(category=category, status=status, limit=limit)
        return {"diseases": diseases}
    except Exception as e:
        logger.error("获取病种列表失败: %s", e)
        raise HTTPException(status_code=502, detail=f"规则核心服务不可用: {e}")


@router.get("/diseases/{disease_id}")
async def get_disease_detail(disease_id: str):
    """获取病种详情"""
    try:
        client = get_rule_core_client()
        detail = await client.get_disease_detail(disease_id)
        return detail
    except Exception as e:
        logger.error("获取病种详情失败: %s -> %s", disease_id, e)
        raise HTTPException(status_code=502, detail=f"规则核心服务不可用: {e}")


# ---- 表型规则 ----

@router.get("/phenotypes")
async def list_phenotype_rules(
    disease_id: Optional[str] = Query(None, description="病种ID过滤"),
    limit: int = Query(50, ge=1, le=200),
):
    """获取表型规则列表"""
    try:
        client = get_rule_core_client()
        rules = await client.list_phenotype_rules(disease_id=disease_id, limit=limit)
        return {"rules": rules}
    except Exception as e:
        logger.error("获取表型规则列表失败: %s", e)
        raise HTTPException(status_code=502, detail=f"规则核心服务不可用: {e}")


@router.get("/phenotypes/{rule_id}")
async def get_phenotype_rule(rule_id: str):
    """获取表型规则详情"""
    try:
        client = get_rule_core_client()
        detail = await client.get_phenotype_rule(rule_id)
        return detail
    except Exception as e:
        logger.error("获取表型规则详情失败: %s -> %s", rule_id, e)
        raise HTTPException(status_code=502, detail=f"规则核心服务不可用: {e}")
