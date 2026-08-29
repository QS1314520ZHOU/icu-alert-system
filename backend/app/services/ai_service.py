"""AI 咨询服务 - MongoDB 实现。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.models.disease_center import AiProposal, AiProposalStatus
from app.repositories import AiProposalRepository


# 仓储实例
_repo = AiProposalRepository()


def _generate_id() -> str:
    """生成唯一ID。"""
    import uuid
    return str(uuid.uuid4())


async def list_proposals(
    disease_id: Optional[str] = None,
    proposal_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> list[AiProposal]:
    """获取 AI 提案列表。"""
    proposals = await _repo.find_all(disease_id, proposal_type, status, limit)
    return [AiProposal(**p) for p in proposals]


async def get_proposal(proposal_id: str) -> Optional[AiProposal]:
    """获取 AI 提案详情。"""
    proposal = await _repo.find_by_id(proposal_id)
    if proposal:
        return AiProposal(**proposal)
    return None


async def create_proposal(
    disease_id: str,
    proposal_type: str,
    title: str,
    content: str,
    context: dict[str, Any],
    confidence: float,
    model_id: str,
    model_version: str,
) -> AiProposal:
    """创建 AI 提案。"""
    proposal = AiProposal(
        id=_generate_id(),
        disease_id=disease_id,
        proposal_type=proposal_type,
        title=title,
        content=content,
        context=context,
        confidence=confidence,
        model_id=model_id,
        model_version=model_version,
        status=AiProposalStatus.PENDING,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    await _repo.create(proposal.model_dump())
    return proposal


async def approve_proposal(proposal_id: str, reviewer_id: str) -> Optional[AiProposal]:
    """通过 AI 提案。"""
    proposal = await get_proposal(proposal_id)
    if not proposal:
        return None

    proposal.status = AiProposalStatus.APPROVED
    proposal.reviewer_id = reviewer_id
    proposal.reviewed_at = datetime.utcnow()
    proposal.updated_at = datetime.utcnow()

    await _repo.update(proposal_id, proposal.model_dump())
    return proposal


async def reject_proposal(
    proposal_id: str,
    reviewer_id: str,
    reason: str,
) -> Optional[AiProposal]:
    """拒绝 AI 提案。"""
    proposal = await get_proposal(proposal_id)
    if not proposal:
        return None

    proposal.status = AiProposalStatus.REJECTED
    proposal.reviewer_id = reviewer_id
    proposal.reviewed_at = datetime.utcnow()
    proposal.rejection_reason = reason
    proposal.updated_at = datetime.utcnow()

    await _repo.update(proposal_id, proposal.model_dump())
    return proposal


async def get_ai_stats() -> dict[str, Any]:
    """获取 AI 咨询统计。"""
    return await _repo.get_stats()
