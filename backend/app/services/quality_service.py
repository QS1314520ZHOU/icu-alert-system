"""质量监控服务 - MongoDB 实现。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.models.disease_center import QualitySnapshot
from app.repositories import QualityRepository


# 仓储实例
_repo = QualityRepository()


def _generate_id() -> str:
    """生成唯一ID。"""
    import uuid
    return str(uuid.uuid4())


async def list_snapshots(
    disease_id: Optional[str] = None,
    limit: int = 100,
) -> list[QualitySnapshot]:
    """获取质量快照列表。"""
    snapshots = await _repo.find_all(disease_id, limit)
    return [QualitySnapshot(**s) for s in snapshots]


async def get_snapshot(snapshot_id: str) -> Optional[QualitySnapshot]:
    """获取质量快照详情。"""
    snapshot = await _repo.find_by_id(snapshot_id)
    if snapshot:
        return QualitySnapshot(**snapshot)
    return None


async def create_snapshot(
    disease_id: str,
    metrics: dict[str, Any],
    issues: list[dict[str, Any]],
    generated_by: str,
) -> QualitySnapshot:
    """创建质量快照。"""
    snapshot = QualitySnapshot(
        id=_generate_id(),
        disease_id=disease_id,
        metrics=QualityMetrics(**metrics),
        issues=issues,
        generated_at=datetime.utcnow(),
        generated_by=generated_by,
    )

    await _repo.create(snapshot.model_dump())
    return snapshot


async def get_quality_summary(disease_id: str) -> dict[str, Any]:
    """获取质量摘要。"""
    snapshots = await _repo.find_by_disease(disease_id)

    if not snapshots:
        return {
            "disease_id": disease_id,
            "total_snapshots": 0,
            "latest_score": None,
            "issues_count": 0,
        }

    latest = snapshots[0]  # 已按时间排序

    return {
        "disease_id": disease_id,
        "total_snapshots": len(snapshots),
        "latest_score": latest.get("metrics", {}).get("overall_score"),
        "latest_snapshot_id": latest.get("id"),
        "issues_count": len(latest.get("issues", [])),
        "metrics": latest.get("metrics", {}),
    }


async def get_quality_trend(
    disease_id: str,
    days: int = 30,
) -> list[dict[str, Any]]:
    """获取质量趋势。"""
    snapshots = await _repo.find_by_disease(disease_id)

    trend = []
    for s in snapshots:
        trend.append({
            "date": s.get("generated_at", "").isoformat() if isinstance(s.get("generated_at"), datetime) else str(s.get("generated_at", "")),
            "score": s.get("metrics", {}).get("overall_score", 0),
            "issues_count": len(s.get("issues", [])),
        })

    return trend


async def run_quality_check(disease_id: str) -> dict[str, Any]:
    """运行质量检查。"""
    # TODO: 实际质量检查逻辑
    # 1. 检查病种定义完整性
    # 2. 检查规则包一致性
    # 3. 检查术语映射完整性
    # 4. 检查临床路径有效性

    issues = []
    score = 100.0

    return {
        "disease_id": disease_id,
        "score": score,
        "issues": issues,
        "passed": len(issues) == 0,
    }
