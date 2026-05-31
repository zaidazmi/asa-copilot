---
name: asa-copilot
description: Operate Apple Search Ads accounts with the asa-copilot CLI. Use for campaign setup, audits, keyword mining, bid/budget recommendations, reporting, decision logs, and safe apply workflows for iOS apps.
allowed-tools: Bash, Read, Grep, Glob
---

# ASA Copilot

Use this skill when an agent needs to inspect, plan, or operate Apple Search Ads through the local `asa` CLI.

## Principles

- Prefer reviewable plans before changing live accounts: `--out plan.json`, `asa plan show`, then `asa apply`.
- Saved plans include app identity; apply should only run under the matching active app.
- Every serving or spend mutation needs a clear reason. Use `--reason` for direct commands and `--note` when applying plans.
- Treat Discovery as learning, exact campaigns as control, and negatives as guardrails against duplicate spend.
- Use app scoping in multi-app setups: `asa --app <name> ...`; explicit campaign IDs are blocked when their `adamId` belongs to another active app.
- Never push live changes from reports alone; turn recommendations into a plan or use an explicit mutating command.

## Common Commands

```bash
asa config setup
asa config test
asa campaigns audit
asa campaigns setup --dry-run
asa campaigns setup --reason "Create guided campaign structure"
```

```bash
asa reports summary --days 7
asa reports keywords --sort cpa
asa reports search-terms --days 14
asa reports bid-recommendations --out bid-plan.json
```

```bash
asa search-terms mine --days 14 --out search-plan.json
asa budget pacing --days 7 --out budget-plan.json
asa optimize --lookback 14d --out optimize-plan.json
asa plan show optimize-plan.json
asa apply optimize-plan.json --note "Approved after CPA and spend review"
```

```bash
asa keywords add "keyword one,keyword two" --type category --reason "Expand exact coverage"
asa keywords promote "winning term" --target category --reason "Promote converting Discovery term"
asa keywords add-negatives "bad term" --all --reason "Block irrelevant spend"
asa campaigns pause 123456789 --reason "Pause duplicate or inefficient campaign"
asa budget create --name "June" --budget 5000 --start 2026-06-01 --end 2026-06-30 --reason "Fund approved monthly plan"
```

## Built Features

- Multi-app config and app-scoped operations.
- Campaign setup, audit, create/update/clone/pause/enable/delete.
- Ad group create/update/pause/enable/delete.
- Keyword routing, promotion, negative management, bid updates, and bulk changes.
- Search-term mining into reviewable plans.
- Bid, lifecycle, hygiene, and budget pacing recommendations from configurable rules.
- Campaign, ad group, keyword, search-term, impression-share, ad, and custom reports.
- Budget order listing/status/pacing/create.
- Geo targeting search/show/set.
- Ad variation, creative, product page, and rejection inspection.
- ACL/current-user/app-search/eligibility/country tools.
- Decision log: `asa decisions list/show/export`.

## Safety Checklist

Before applying changes:

- Run the relevant report/audit first.
- Save recommendations to a plan when possible.
- Confirm each executable action has a reason.
- Check planned campaign IDs, ad group IDs, country codes, bids, and budgets.
- After applying, review `asa decisions list` and schedule a follow-up window.
