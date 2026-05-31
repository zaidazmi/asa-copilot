"""Durable decision log for ASA operator changes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from .config import CONFIG_DIR, get_current_app_config, ensure_config_dir

DECISION_LOG_FILE = CONFIG_DIR / "decision-log.jsonl"


class DecisionRecord(BaseModel):
    """One human-readable decision/audit record."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type: str
    reason: str
    source: str = "manual"
    actor: str = "cli"
    app_id: Optional[int] = None
    app_name: Optional[str] = None
    command: Optional[str] = None
    note: Optional[str] = None
    plan_id: Optional[str] = None
    action_id: Optional[str] = None
    action_type: Optional[str] = None
    campaign_id: Optional[int] = None
    campaign_name: Optional[str] = None
    ad_group_id: Optional[int] = None
    ad_group_name: Optional[str] = None
    keyword_id: Optional[int] = None
    keywords: list[str] = Field(default_factory=list)
    expected_outcome: Optional[str] = None
    follow_up_window: Optional[str] = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)


def append_decision(record: DecisionRecord, path: Optional[Path] = None) -> None:
    """Append a decision record to the local decision log."""
    path = path or DECISION_LOG_FILE
    ensure_config_dir()
    with open(path, "a") as f:
        f.write(record.model_dump_json())
        f.write("\n")


def load_decisions(path: Optional[Path] = None) -> list[DecisionRecord]:
    """Load all decision records from JSONL, skipping malformed blank lines."""
    path = path or DECISION_LOG_FILE
    if not path.exists():
        return []

    records: list[DecisionRecord] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(DecisionRecord(**json.loads(line)))
    return records


def find_decision(decision_id: str, path: Optional[Path] = None) -> Optional[DecisionRecord]:
    """Find a decision by full id or unique prefix."""
    matches = [record for record in load_decisions(path) if record.id.startswith(decision_id)]
    if len(matches) == 1:
        return matches[0]
    return None


def log_manual_decision(
    *,
    event_type: str,
    reason: str,
    source: str = "manual",
    actor: str = "cli",
    command: Optional[str] = None,
    app_id: Optional[int] = None,
    app_name: Optional[str] = None,
    note: Optional[str] = None,
    campaign_id: Optional[int] = None,
    campaign_name: Optional[str] = None,
    ad_group_id: Optional[int] = None,
    ad_group_name: Optional[str] = None,
    keyword_id: Optional[int] = None,
    keywords: Optional[list[str]] = None,
    expected_outcome: Optional[str] = None,
    follow_up_window: Optional[str] = None,
    evidence: Optional[dict[str, Any]] = None,
    metadata: Optional[dict[str, Any]] = None,
    result: Optional[dict[str, Any]] = None,
) -> DecisionRecord:
    """Create and append a manual/direct command decision."""
    app_config = get_current_app_config()
    record = DecisionRecord(
        event_type=event_type,
        reason=reason,
        source=source,
        actor=actor,
        command=command,
        app_id=app_id if app_id is not None else (app_config.app_id if app_config else None),
        app_name=app_name or (app_config.app_name if app_config else None),
        note=note,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        ad_group_id=ad_group_id,
        ad_group_name=ad_group_name,
        keyword_id=keyword_id,
        keywords=keywords or [],
        expected_outcome=expected_outcome,
        follow_up_window=follow_up_window,
        evidence=evidence or {},
        metadata=metadata or {},
        result=result or {},
    )
    append_decision(record)
    return record


def log_applied_plan_decisions(
    plan,
    apply_result,
    *,
    actor: str = "cli",
    approval_note: Optional[str] = None,
    path: Path = DECISION_LOG_FILE,
) -> list[DecisionRecord]:
    """Write one decision record for each applied plan action."""
    result_by_action = {result.action_id: result for result in apply_result.results}
    records: list[DecisionRecord] = []

    for action in plan.actions:
        result = result_by_action.get(action.id)
        record = DecisionRecord(
            event_type="plan_action_applied",
            reason=action.reason or "Legacy plan action without reason",
            source=action.source or plan.source,
            actor=actor,
            app_id=getattr(plan, "app_id", None),
            app_name=plan.app_name,
            note=approval_note,
            plan_id=plan.id,
            action_id=action.id,
            action_type=action.type.value,
            campaign_id=action.campaign_id,
            campaign_name=action.campaign_name,
            ad_group_id=action.ad_group_id,
            ad_group_name=action.ad_group_name,
            keyword_id=action.keyword_id,
            keywords=action.keywords,
            evidence=action.before_metrics,
            metadata=action.metadata,
            result=result.model_dump(mode="json") if result else {},
        )
        append_decision(record, path=path)
        records.append(record)

    return records


def decisions_to_markdown(records: list[DecisionRecord]) -> str:
    """Render decision records as compact Markdown."""
    lines = ["# ASA Decision Log", ""]
    for record in records:
        target = record.campaign_name or str(record.campaign_id or "")
        if record.ad_group_name:
            target = f"{target} / {record.ad_group_name}".strip(" /")
        lines.extend(
            [
                f"## {record.created_at} - {record.event_type}",
                "",
                f"- ID: `{record.id}`",
                f"- Source: `{record.source}`",
                f"- Actor: `{record.actor}`",
                f"- Reason: {record.reason}",
            ]
        )
        if record.app_id or record.app_name:
            app_label = record.app_name or ""
            if record.app_id:
                app_label = f"{app_label} ({record.app_id})".strip()
            lines.append(f"- App: {app_label}")
        if target:
            lines.append(f"- Target: {target}")
        if record.plan_id:
            lines.append(f"- Plan: `{record.plan_id}`")
        if record.action_type:
            lines.append(f"- Action: `{record.action_type}`")
        if record.note:
            lines.append(f"- Note: {record.note}")
        lines.append("")
    return "\n".join(lines)
