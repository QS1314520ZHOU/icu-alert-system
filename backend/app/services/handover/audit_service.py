"""
Handover — Audit Service.

Manages version snapshots, frozen data, acknowledgment records, and audit logging.
Every confirm transitions the document through a three-part snapshot:
  1. Raw clinical data snapshot (with data_snapshot_at timestamp)
  2. AI first-generation content
  3. Handover operator's final confirmed content
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.services.handover.schemas import (
    ContentSource,
    HandoverDocument,
    HandoverStatus,
    VersionSnapshot,
)

API_TZ = ZoneInfo("Asia/Shanghai")
logger = logging.getLogger("icu-alert")

COLLECTION_AUDIT = "handover_audit_logs"


class HandoverAuditService:
    """Handles versioning, snapshot freezing, acknowledgment, and audit trails."""

    def __init__(self, db) -> None:
        self.db = db

    def _now(self) -> str:
        return datetime.now(API_TZ).isoformat()

    # ── Version Management ─────────────────────────────────────────

    def create_version(
        self,
        doc: HandoverDocument,
        data_snapshot: dict[str, Any],
        ai_first_draft: dict[str, Any] | None,
        created_by: str,
        change_note: str = "",
    ) -> VersionSnapshot:
        """Capture a frozen version snapshot of the current document state."""
        version_num = len(doc.versions) + 1
        snapshot = VersionSnapshot(
            version=version_num,
            sections=doc.sections,
            data_snapshot=data_snapshot,
            ai_first_draft=ai_first_draft,
            created_by=created_by,
            created_at=self._now(),
            change_note=change_note,
        )
        return snapshot

    def append_version(
        self,
        doc: HandoverDocument,
        data_snapshot: dict[str, Any],
        ai_first_draft: dict[str, Any] | None,
        created_by: str,
        change_note: str = "",
    ) -> None:
        """Append a version snapshot to the document's version chain."""
        snapshot = self.create_version(doc, data_snapshot, ai_first_draft, created_by, change_note)
        doc.versions.append(snapshot)

    # ── Status Transitions ─────────────────────────────────────────

    VALID_TRANSITIONS: dict[HandoverStatus, set[HandoverStatus]] = {
        HandoverStatus.NOT_CREATED: {HandoverStatus.DRAFT},
        HandoverStatus.DRAFT: {HandoverStatus.DRAFT, HandoverStatus.PENDING},
        HandoverStatus.PENDING: {HandoverStatus.DRAFT, HandoverStatus.SUBMITTED},
        HandoverStatus.SUBMITTED: {HandoverStatus.DRAFT, HandoverStatus.ACKNOWLEDGED},
        HandoverStatus.ACKNOWLEDGED: {HandoverStatus.DRAFT},  # creates new version, original stays acknowledged
    }

    def can_transition(self, current: HandoverStatus, target: HandoverStatus) -> bool:
        """Check if the status transition is allowed."""
        return target in self.VALID_TRANSITIONS.get(current, set())

    def transition(
        self,
        doc: HandoverDocument,
        target: HandoverStatus,
        *,
        operator: str = "",
        reason: str = "",
    ) -> HandoverDocument:
        """Apply a status transition with audit logging.

        Raises ValueError if the transition is invalid.
        """
        if not self.can_transition(doc.status, target):
            raise ValueError(
                f"Invalid status transition: {doc.status.value} → {target.value}"
            )

        old_status = doc.status
        doc.status = target
        doc.updated_at = self._now()

        # Handle transition-specific updates
        if target == HandoverStatus.SUBMITTED:
            doc.submitted_by = operator
            doc.submitted_at = self._now()
        elif target == HandoverStatus.ACKNOWLEDGED:
            doc.acknowledged_by = operator
            doc.acknowledged_at = self._now()
        elif target == HandoverStatus.DRAFT and old_status == HandoverStatus.ACKNOWLEDGED:
            # Re-open creates a new version; old acknowledged version is preserved
            pass

        # Log the transition
        logger.info(
            "handover %s: %s → %s by %s (reason: %s)",
            doc.handover_id, old_status.value, target.value, operator, reason,
        )
        return doc

    # ── Content Editing & Source Tracking ──────────────────────────

    def mark_field_sources(
        self,
        doc: HandoverDocument,
        edited_fields: list[str],
        operator: str = "",
    ) -> None:
        """Mark which fields were edited by a human operator."""
        for field_path in edited_fields:
            # Mark as human-modified if previously AI-generated
            if doc.content_sources.get(field_path) == ContentSource.AI_GENERATED.value:
                doc.content_sources[field_path] = ContentSource.HUMAN_MODIFIED.value
            else:
                doc.content_sources[field_path] = ContentSource.HUMAN_MODIFIED.value

        # Remove edited fields from ai_generated_fields if present
        doc.ai_generated_fields = [
            f for f in doc.ai_generated_fields if f not in edited_fields
        ]

    # ── Forced Confirmations ───────────────────────────────────────

    def update_forced_confirmations(
        self,
        doc: HandoverDocument,
        confirmations: list[dict[str, Any]],
        operator: str,
    ) -> None:
        """Update the status of forced confirmation items during acknowledgment."""
        now = self._now()
        for conf in confirmations:
            item_id = str(conf.get("item_id", ""))
            for fc in doc.forced_confirmations:
                if fc.item_id == item_id:
                    fc.confirmed = bool(conf.get("confirmed", False))
                    fc.confirmed_by = operator
                    fc.confirmed_at = now
                    break

    def all_forced_confirmed(self, doc: HandoverDocument) -> bool:
        """Check if all forced confirmation items have been confirmed."""
        if not doc.forced_confirmations:
            return True
        return all(fc.confirmed for fc in doc.forced_confirmations)

    # ── Audit Log ──────────────────────────────────────────────────

    async def log_event(
        self,
        handover_id: str,
        patient_id: str,
        event_type: str,
        operator: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Write an audit log entry."""
        try:
            await self.db.col(COLLECTION_AUDIT).insert_one({
                "handover_id": handover_id,
                "patient_id": patient_id,
                "event_type": event_type,
                "operator": operator,
                "details": details or {},
                "timestamp": self._now(),
            })
        except Exception as exc:
            logger.error("handover audit log write failed: %s", exc)

    # ── Snapshot History ───────────────────────────────────────────

    def get_latest_version(self, doc: HandoverDocument) -> VersionSnapshot | None:
        """Return the most recent version snapshot, if any."""
        if doc.versions:
            return doc.versions[-1]
        return None

    def get_version_diff(
        self, doc: HandoverDocument, v1: int, v2: int
    ) -> dict[str, Any]:
        """Return a simple diff between two versions (placeholder — full diff in Phase 2)."""
        snap1 = next((v for v in doc.versions if v.version == v1), None)
        snap2 = next((v for v in doc.versions if v.version == v2), None)
        if not snap1 or not snap2:
            return {"error": "version not found"}
        return {
            "v1": v1,
            "v2": v2,
            "v1_created_at": snap1.created_at,
            "v2_created_at": snap2.created_at,
        }
