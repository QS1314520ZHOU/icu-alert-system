"""
规则核心 HTTP 客户端
用于与 critical-care-alert-platform 规则核心服务通信
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import get_config

logger = logging.getLogger(__name__)


class RuleCoreClient:
    """规则核心 HTTP 客户端"""

    def __init__(self, base_url: str | None = None):
        self._base_url = (base_url or get_config().rule_core_url).rstrip("/")
        self._timeout = 30.0

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """发送 HTTP 请求到规则核心"""
        url = f"{self._base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=timeout or self._timeout) as client:
                resp = await client.request(method, url, json=json, params=params)
                resp.raise_for_status()
                return resp.json()
        except httpx.TimeoutException:
            logger.error("规则核心请求超时: %s %s", method, url)
            raise
        except httpx.HTTPStatusError as e:
            logger.error("规则核心返回错误: %s %s -> %d", method, url, e.response.status_code)
            raise
        except Exception as e:
            logger.error("规则核心请求失败: %s %s -> %s", method, url, e)
            raise

    # ---- 评分系统 ----

    async def list_scoring_systems(self) -> list[dict[str, Any]]:
        """获取所有评分系统列表"""
        result = await self._request("GET", "/api/scoring/systems")
        return result if isinstance(result, list) else result.get("systems", [])

    async def get_scoring_rule(self, rule_id: str) -> dict[str, Any]:
        """获取评分规则详情"""
        return await self._request("GET", f"/api/scoring/rules/{rule_id}")

    async def evaluate_score(
        self,
        patient_id: str,
        score_system: str,
        *,
        score_variant: str | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行评分计算"""
        payload: dict[str, Any] = {
            "patient_id": patient_id,
            "score_system": score_system,
        }
        if score_variant:
            payload["score_variant"] = score_variant
        if inputs:
            payload["inputs"] = inputs
        return await self._request("POST", "/api/scoring/evaluate", json=payload)

    async def run_test_case(
        self,
        rule_id: str,
        test_case: dict[str, Any],
    ) -> dict[str, Any]:
        """执行测试病例"""
        return await self._request(
            "POST",
            "/api/scoring/test-case",
            json={"rule_id": rule_id, "test_case": test_case},
        )

    # ---- 术语编码 ----

    async def search_terminology(
        self,
        query: str,
        *,
        category: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """搜索术语"""
        params: dict[str, Any] = {"q": query, "limit": limit}
        if category:
            params["category"] = category
        result = await self._request("GET", "/api/terminology/search", params=params)
        return result if isinstance(result, list) else result.get("items", [])

    async def get_terminology_detail(self, term_id: str) -> dict[str, Any]:
        """获取术语详情"""
        return await self._request("GET", f"/api/terminology/{term_id}")

    async def list_terminology_categories(self) -> list[dict[str, Any]]:
        """获取术语分类列表"""
        result = await self._request("GET", "/api/terminology/categories")
        return result if isinstance(result, list) else result.get("categories", [])

    # ---- 病种 ----

    async def list_diseases(
        self,
        *,
        category: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """获取病种列表"""
        params: dict[str, Any] = {"limit": limit}
        if category:
            params["category"] = category
        if status:
            params["status"] = status
        result = await self._request("GET", "/api/diseases", params=params)
        return result if isinstance(result, list) else result.get("diseases", [])

    async def get_disease_detail(self, disease_id: str) -> dict[str, Any]:
        """获取病种详情"""
        return await self._request("GET", f"/api/diseases/{disease_id}")

    # ---- 表型规则 ----

    async def list_phenotype_rules(
        self,
        *,
        disease_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """获取表型规则列表"""
        params: dict[str, Any] = {"limit": limit}
        if disease_id:
            params["disease_id"] = disease_id
        result = await self._request("GET", "/api/phenotypes", params=params)
        return result if isinstance(result, list) else result.get("rules", [])

    async def get_phenotype_rule(self, rule_id: str) -> dict[str, Any]:
        """获取表型规则详情"""
        return await self._request("GET", f"/api/phenotypes/{rule_id}")

    # ---- 健康检查 ----

    async def health_check(self) -> dict[str, Any]:
        """检查规则核心健康状态"""
        try:
            return await self._request("GET", "/health", timeout=5.0)
        except Exception:
            return {"status": "unavailable"}


# 单例
_rule_core_client: RuleCoreClient | None = None


def get_rule_core_client() -> RuleCoreClient:
    """获取规则核心客户端单例"""
    global _rule_core_client
    if _rule_core_client is None:
        _rule_core_client = RuleCoreClient()
    return _rule_core_client
