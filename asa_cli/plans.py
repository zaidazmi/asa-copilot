"""Plan models and apply engine for spend-affecting ASA changes."""

from __future__ import annotations

import json
from json import JSONDecodeError
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from .api import SearchAdsClient
from .config import CONFIG_DIR, AppConfig, MatchType, campaign_matches_app, ensure_config_dir
from .decisions import log_applied_plan_decisions

console = Console()

PLAN_SCHEMA_VERSION = "1.0"
APPLIED_PLANS_FILE = CONFIG_DIR / "applied-plans.jsonl"


class PlanLoadError(ValueError):
    """Raised when a plan file cannot be loaded or validated."""


class PlanReasonError(ValueError):
    """Raised when executable plan actions are missing reasons."""


class PlanScopeError(ValueError):
    """Raised when a plan targets a different app than the active app."""


class PlanActionType(str, Enum):
    """Supported plan action types."""

    ADD_KEYWORDS = "add_keywords"
    ADD_NEGATIVE_KEYWORDS = "add_negative_keywords"
    UPDATE_KEYWORD_BID = "update_keyword_bid"
    PAUSE_KEYWORD = "pause_keyword"
    PAUSE_CAMPAIGN = "pause_campaign"
    ENABLE_CAMPAIGN = "enable_campaign"
    CLONE_CAMPAIGN = "clone_campaign"
    CREATE_CAMPAIGN = "create_campaign"
    CREATE_AD_GROUP = "create_ad_group"
    UPDATE_AD_GROUP = "update_ad_group"
    UPDATE_CAMPAIGN_BUDGET = "update_campaign_budget"
    CREATIVE_MAPPING_CHECK = "creative_mapping_check"


EXECUTABLE_ACTION_TYPES = {
    PlanActionType.ADD_KEYWORDS,
    PlanActionType.ADD_NEGATIVE_KEYWORDS,
    PlanActionType.UPDATE_KEYWORD_BID,
    PlanActionType.PAUSE_KEYWORD,
    PlanActionType.PAUSE_CAMPAIGN,
    PlanActionType.ENABLE_CAMPAIGN,
    PlanActionType.CLONE_CAMPAIGN,
    PlanActionType.CREATE_CAMPAIGN,
    PlanActionType.CREATE_AD_GROUP,
    PlanActionType.UPDATE_AD_GROUP,
    PlanActionType.UPDATE_CAMPAIGN_BUDGET,
}


class PlanAction(BaseModel):
    """One executable or informational change inside a plan."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    type: PlanActionType
    description: str
    campaign_id: Optional[int] = None
    campaign_name: Optional[str] = None
    ad_group_id: Optional[int] = None
    ad_group_name: Optional[str] = None
    keyword_id: Optional[int] = None
    keywords: list[str] = Field(default_factory=list)
    match_type: Optional[MatchType] = None
    bid_amount: Optional[float] = None
    daily_budget_amount: Optional[float] = None
    reason: Optional[str] = None
    source: str = "manual"
    before_metrics: dict[str, Any] = Field(default_factory=dict)
    after_metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChangePlan(BaseModel):
    """A durable plan that can be reviewed and applied later."""

    schema_version: str = PLAN_SCHEMA_VERSION
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "manual"
    app_id: Optional[int] = None
    app_name: Optional[str] = None
    lookback_days: Optional[int] = None
    summary: str = ""
    actions: list[PlanAction] = Field(default_factory=list)


class ApplyActionResult(BaseModel):
    """Result for one attempted action."""

    action_id: str
    action_type: PlanActionType
    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class ApplyPlanResult(BaseModel):
    """Aggregate result for applying a plan."""

    plan_id: str
    applied_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    success: bool
    results: list[ApplyActionResult]


def load_plan(path: Path) -> ChangePlan:
    """Load a change plan from JSON."""
    try:
        with open(path) as f:
            data = json.load(f)
        return ChangePlan(**data)
    except FileNotFoundError as exc:
        raise PlanLoadError(f"Plan file not found: {path}") from exc
    except JSONDecodeError as exc:
        raise PlanLoadError(f"Plan file is not valid JSON: {path} ({exc.msg})") from exc
    except (TypeError, ValidationError) as exc:
        raise PlanLoadError(f"Plan file does not match the plan schema: {path} ({exc})") from exc


def save_plan(plan: ChangePlan, path: Path) -> None:
    """Write a change plan to JSON."""
    validate_plan_reasons(plan)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(plan.model_dump_json(indent=2))
        f.write("\n")


def save_applied_plan(
    plan: ChangePlan,
    result: ApplyPlanResult,
    *,
    actor: str = "cli",
    approval_note: Optional[str] = None,
) -> None:
    """Append an applied plan record to local audit history."""
    ensure_config_dir()
    record = {
        "plan": plan.model_dump(mode="json"),
        "result": result.model_dump(mode="json"),
    }
    with open(APPLIED_PLANS_FILE, "a") as f:
        f.write(json.dumps(record, default=str))
        f.write("\n")
    log_applied_plan_decisions(plan, result, actor=actor, approval_note=approval_note)


def missing_reason_actions(plan: ChangePlan) -> list[PlanAction]:
    """Return executable actions that do not explain why they exist."""
    return [
        action
        for action in plan.actions
        if action.type in EXECUTABLE_ACTION_TYPES and not (action.reason or "").strip()
    ]


def validate_plan_reasons(plan: ChangePlan) -> None:
    """Require reasons before new plans can be saved or applied."""
    missing = missing_reason_actions(plan)
    if not missing:
        return
    details = ", ".join(f"{action.type.value}:{action.id}" for action in missing[:5])
    if len(missing) > 5:
        details += f", ... ({len(missing)} total)"
    raise PlanReasonError(f"Executable plan actions require reasons: {details}")


def _client_app_config(client: SearchAdsClient) -> Optional[AppConfig]:
    app_config = getattr(client, "app_config", None)
    return app_config if isinstance(app_config, AppConfig) else None


def validate_plan_app_scope(client: SearchAdsClient, plan: ChangePlan) -> None:
    """Reject plans created for another app before applying any action."""
    app_config = _client_app_config(client)
    if app_config is None or plan.app_id is None:
        return
    if int(plan.app_id) != int(app_config.app_id):
        raise PlanScopeError(
            f"Plan targets app {plan.app_id}, but active app is "
            f"{app_config.app_name} ({app_config.app_id})."
        )


def validate_action_app_scope(client: SearchAdsClient, action: PlanAction) -> Optional[str]:
    """Return an error when an action's campaign is outside the active app."""
    app_config = _client_app_config(client)
    if app_config is None or action.campaign_id is None:
        return None

    campaign = client.get_campaign(action.campaign_id)
    if not campaign:
        return f"Campaign {action.campaign_id} not found"
    if not campaign_matches_app(campaign, app_config):
        return (
            f"Campaign {action.campaign_id} belongs to app "
            f"{campaign.get('adamId', 'unknown')}, not active app "
            f"{app_config.app_name} ({app_config.app_id})"
        )
    return None


def _duplicate_errors_only(errors: list[dict[str, Any]]) -> bool:
    return bool(errors) and all(e.get("messageCode") == "DUPLICATE_KEYWORD" for e in errors)


def apply_action(client: SearchAdsClient, action: PlanAction) -> ApplyActionResult:
    """Apply a single plan action."""
    try:
        if action.type in EXECUTABLE_ACTION_TYPES:
            scope_error = validate_action_app_scope(client, action)
            if scope_error:
                return ApplyActionResult(
                    action_id=action.id,
                    action_type=action.type,
                    success=False,
                    message=scope_error,
                )

        if action.type == PlanActionType.ADD_KEYWORDS:
            if action.campaign_id is None or action.ad_group_id is None:
                return ApplyActionResult(
                    action_id=action.id,
                    action_type=action.type,
                    success=False,
                    message="Missing campaign_id or ad_group_id",
                )
            added, errors = client.add_keywords(
                campaign_id=action.campaign_id,
                ad_group_id=action.ad_group_id,
                keywords=action.keywords,
                match_type=action.match_type or MatchType.EXACT,
                bid_amount=action.bid_amount,
            )
            if errors and not _duplicate_errors_only(errors):
                return ApplyActionResult(
                    action_id=action.id,
                    action_type=action.type,
                    success=False,
                    message=errors[0].get("message", "Failed to add keywords"),
                    data={"errors": errors},
                )
            message = f"Added {len(added) if added else len(action.keywords)} keywords"
            if _duplicate_errors_only(errors):
                message = f"{len(errors)} keywords already existed"
            return ApplyActionResult(
                action_id=action.id,
                action_type=action.type,
                success=True,
                message=message,
                data={"added": added, "errors": errors},
            )

        if action.type == PlanActionType.ADD_NEGATIVE_KEYWORDS:
            if action.campaign_id is None:
                return ApplyActionResult(
                    action_id=action.id,
                    action_type=action.type,
                    success=False,
                    message="Missing campaign_id",
                )
            added, errors = client.add_negative_keywords(
                campaign_id=action.campaign_id,
                keywords=action.keywords,
                match_type=action.match_type or MatchType.EXACT,
            )
            if errors and not _duplicate_errors_only(errors):
                return ApplyActionResult(
                    action_id=action.id,
                    action_type=action.type,
                    success=False,
                    message=errors[0].get("message", "Failed to add negative keywords"),
                    data={"errors": errors},
                )
            message = f"Added {len(added) if added else len(action.keywords)} negative keywords"
            if _duplicate_errors_only(errors):
                message = f"{len(errors)} negative keywords already existed"
            return ApplyActionResult(
                action_id=action.id,
                action_type=action.type,
                success=True,
                message=message,
                data={"added": added, "errors": errors},
            )

        if action.type == PlanActionType.UPDATE_KEYWORD_BID:
            if (
                action.campaign_id is None
                or action.ad_group_id is None
                or action.keyword_id is None
            ):
                return ApplyActionResult(
                    action_id=action.id,
                    action_type=action.type,
                    success=False,
                    message="Missing campaign_id, ad_group_id, or keyword_id",
                )
            if action.bid_amount is None:
                return ApplyActionResult(
                    action_id=action.id,
                    action_type=action.type,
                    success=False,
                    message="Missing bid_amount",
                )
            updated = client.update_keyword_bid(
                action.campaign_id,
                action.ad_group_id,
                action.keyword_id,
                action.bid_amount,
            )
            return ApplyActionResult(
                action_id=action.id,
                action_type=action.type,
                success=updated is not None,
                message=(
                    "Updated keyword bid" if updated is not None else "Failed to update keyword bid"
                ),
                data={"updated": updated or []},
            )

        if action.type == PlanActionType.PAUSE_KEYWORD:
            if (
                action.campaign_id is None
                or action.ad_group_id is None
                or action.keyword_id is None
            ):
                return ApplyActionResult(
                    action_id=action.id,
                    action_type=action.type,
                    success=False,
                    message="Missing campaign_id, ad_group_id, or keyword_id",
                )
            success = client.pause_keyword(
                action.campaign_id, action.ad_group_id, action.keyword_id
            )
            return ApplyActionResult(
                action_id=action.id,
                action_type=action.type,
                success=success,
                message="Paused keyword" if success else "Failed to pause keyword",
            )

        if action.type == PlanActionType.UPDATE_CAMPAIGN_BUDGET:
            if action.campaign_id is None or action.daily_budget_amount is None:
                return ApplyActionResult(
                    action_id=action.id,
                    action_type=action.type,
                    success=False,
                    message="Missing campaign_id or daily_budget_amount",
                )
            updated = client.update_campaign(
                action.campaign_id,
                {
                    "dailyBudgetAmount": {
                        "amount": str(action.daily_budget_amount),
                        "currency": action.metadata.get("currency", "USD"),
                    }
                },
            )
            return ApplyActionResult(
                action_id=action.id,
                action_type=action.type,
                success=updated is not None,
                message=(
                    "Updated campaign budget" if updated is not None else "Failed to update budget"
                ),
                data={"updated": updated or {}},
            )

        if action.type == PlanActionType.PAUSE_CAMPAIGN:
            if action.campaign_id is None:
                return ApplyActionResult(
                    action_id=action.id,
                    action_type=action.type,
                    success=False,
                    message="Missing campaign_id",
                )
            success = client.pause_campaign(action.campaign_id)
            return ApplyActionResult(
                action_id=action.id,
                action_type=action.type,
                success=success,
                message="Paused campaign" if success else "Failed to pause campaign",
            )

        if action.type == PlanActionType.ENABLE_CAMPAIGN:
            if action.campaign_id is None:
                return ApplyActionResult(
                    action_id=action.id,
                    action_type=action.type,
                    success=False,
                    message="Missing campaign_id",
                )
            success = client.enable_campaign(action.campaign_id)
            return ApplyActionResult(
                action_id=action.id,
                action_type=action.type,
                success=success,
                message="Enabled campaign" if success else "Failed to enable campaign",
            )

        if action.type in {
            PlanActionType.CLONE_CAMPAIGN,
            PlanActionType.CREATE_CAMPAIGN,
            PlanActionType.CREATE_AD_GROUP,
            PlanActionType.UPDATE_AD_GROUP,
        }:
            return ApplyActionResult(
                action_id=action.id,
                action_type=action.type,
                success=False,
                message=f"{action.type.value} is not executable via plan apply yet",
            )

        return ApplyActionResult(
            action_id=action.id,
            action_type=action.type,
            success=True,
            message="Informational check recorded; no API change applied",
        )
    except Exception as exc:
        return ApplyActionResult(
            action_id=action.id,
            action_type=action.type,
            success=False,
            message=str(exc),
        )


def apply_plan(client: SearchAdsClient, plan: ChangePlan) -> ApplyPlanResult:
    """Apply all actions in a plan."""
    validate_plan_reasons(plan)
    validate_plan_app_scope(client, plan)
    results = [apply_action(client, action) for action in plan.actions]
    return ApplyPlanResult(
        plan_id=plan.id,
        success=all(result.success for result in results),
        results=results,
    )


def display_plan(plan: ChangePlan) -> None:
    """Render a plan for human review."""
    console.print(f"[bold]Plan:[/bold] {plan.id}")
    if plan.summary:
        console.print(f"[bold]Summary:[/bold] {plan.summary}")
    if plan.app_name:
        console.print(f"[bold]App:[/bold] {plan.app_name}")
    if plan.lookback_days:
        console.print(f"[bold]Lookback:[/bold] {plan.lookback_days} days")

    table = Table(title="Planned Changes", show_header=True, header_style="bold magenta")
    table.add_column("#", justify="right")
    table.add_column("Type")
    table.add_column("Target")
    table.add_column("Change")
    table.add_column("Reason")

    for idx, action in enumerate(plan.actions, 1):
        target = action.campaign_name or str(action.campaign_id or "-")
        if action.ad_group_name:
            target = f"{target} / {action.ad_group_name}"
        change = action.description
        if action.keywords:
            change = f"{change} ({len(action.keywords)} terms)"
        table.add_row(
            str(idx),
            action.type.value,
            target,
            change,
            action.reason or "",
        )

    console.print(table)


def display_apply_result(result: ApplyPlanResult) -> None:
    """Render apply results for human review."""
    table = Table(title="Apply Results", show_header=True, header_style="bold magenta")
    table.add_column("#", justify="right")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Message")

    for idx, action_result in enumerate(result.results, 1):
        status = "[green]ok[/green]" if action_result.success else "[red]failed[/red]"
        table.add_row(str(idx), action_result.action_type.value, status, action_result.message)

    console.print(table)
    if result.success:
        console.print("[bold green]Plan applied successfully.[/bold green]")
    else:
        console.print("[bold yellow]Plan applied with failures.[/bold yellow]")
