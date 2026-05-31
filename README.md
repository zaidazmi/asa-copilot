# asa-copilot

Apple Search Ads operations from the command line.

`asa-copilot` is an operations CLI for indie iOS developers and small growth teams running Apple Search Ads. It helps you configure apps, audit account structure, mine search terms, manage keywords, pace budgets, and turn optimization ideas into reviewable plans before anything changes in your account.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Apple Ads API v5](https://img.shields.io/badge/Apple%20Ads%20API-v5-black.svg)](https://developer.apple.com/documentation/apple_ads)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

```bash
asa search-terms mine --lookback 14d --out search-term-plan.json
asa plan show search-term-plan.json
asa apply search-term-plan.json
```

## Why It Exists

Apple Ads Manager is good for inspection, but repeated account operations get messy quickly: checking structure, finding wasted search terms, avoiding duplicate keyword spend, adjusting bids, and making sure budget is going to campaigns that actually work.

`asa-copilot` turns those tasks into a safer operator loop:

1. Pull account and report data.
2. Apply configurable rules.
3. Produce a reviewable change plan.
4. Apply only what you approve.
5. Keep a local audit history.

The CLI command is intentionally short:

```bash
asa --help
```

## Core Features

| Area | What it does |
| --- | --- |
| Multi-app config | Manage multiple apps and switch with `asa --app <slug> ...` |
| Plan / apply safety | Save proposed spend-affecting changes to JSON, review them, then apply |
| Decision log | Require reasons for serving/spend changes and store them in a local JSONL log |
| Search-term mining | Promote winners, block losers, and protect Discovery with negatives |
| Guide hygiene | Detect duplicate active keywords, missing Discovery negatives, Search Match drift, and multi-country drift |
| Optimization rules | Raise/lower bids, pause poor keywords, add negatives, and promote terms using configurable thresholds |
| Operator reports | Daily and weekly briefs with spend, installs, CPA, winners, losers, pacing issues, and next actions |
| Budget pacing | Recommend budget increases for capped winners and cuts for inefficient campaigns |
| Campaign tools | Create, clone, update, pause, enable, audit, and list campaigns |
| Keyword tools | Add, route, find, list, promote, bid-update, and manage negative keywords |
| Account tools | ACL, app search, eligibility, geo targeting, ads, creatives, product pages, and rejection checks |

## Install

```bash
git clone https://github.com/zaidazmi/asa-copilot.git
cd asa-copilot
pip install -e .
asa --help
```

For development:

```bash
pip install -e ".[dev]"
pytest
```

## Configure

Run the guided setup:

```bash
asa config setup
asa config test
asa config show
```

Local files live under:

```text
~/.asa-cli/
|-- credentials.json
|-- config.json
|-- rules.json
|-- applied-plans.jsonl
`-- decision-log.jsonl
```

`credentials.json` contains sensitive Apple Ads API credentials. Keep it local and out of git.

### API Credentials

In Apple Ads, open Account Settings, then API. Create or use an API user, upload your public key, and collect:

- Organization ID
- Client ID
- Team ID
- Key ID
- Private key PEM path

Generate an EC key pair locally:

```bash
openssl ecparam -genkey -name prime256v1 -noout -out apple-ads-private-key.pem
openssl ec -in apple-ads-private-key.pem -pubout -out apple-ads-public-key.pem
```

Upload only the public key to Apple. Use the private key path during `asa config setup`.

## The Operator Workflow

### 1. Inspect The Account

```bash
asa campaigns list --all
asa campaigns audit
asa budget status
asa report weekly
```

Use this to understand campaign status, budget health, and recent performance before making changes.

### 2. Manage Campaigns

```bash
asa campaigns setup --countries US --budget 50 --dry-run
asa campaigns setup --countries US --budget 50 --reason "Launch tested Search Results structure"

asa campaigns create "MyApp - Category - Exact - US" --countries US --budget 20 --status PAUSED --reason "Test category exact demand"
asa campaigns update 123456789 --budget 15 --reason "Reduce spend while CPA is above target"
asa campaigns pause 123456789 --reason "Poor CPA after 14 day test"
asa campaigns enable 123456789 --reason "App review issue resolved"
```

Campaign operations are explicit by default. Use campaign IDs when changing live objects. Serving and spend mutations capture a reason, either through `--reason` or an interactive prompt.

### 3. Manage Keywords

```bash
asa keywords add "ai note taker,voice notes" --type category --reason "Expand exact coverage for converting note-taking intent"
asa keywords add "competitor app,another app" --type competitor --reason "Test competitor conquesting at capped bids"
asa keywords add-negatives "free games,testflight" --all --reason "Block irrelevant traffic seen in search terms"

asa keywords list --campaign 123456789
asa keywords find "notes"
asa keywords update-bids-bulk --campaign 123456789 --bid 1.25 --reason "Normalize bids after CPA review"
```

Keyword routing understands the standard Search Results structure:

- brand terms go to brand exact campaigns
- category terms go to category exact campaigns
- competitor terms go to competitor exact campaigns
- discovery receives broad coverage and negatives where appropriate

### 4. Mine Search Terms

Inspect raw search-term data:

```bash
asa reports search-terms --campaign 123456789 --days 14
asa reports search-terms --winners
asa reports search-terms --negatives
```

Generate a reviewable mining plan:

```bash
asa search-terms mine --lookback 14d --out search-term-plan.json
asa plan show search-term-plan.json
```

`asa search-terms mine` can:

- promote winning Discovery terms into exact campaigns
- add promoted terms as Discovery negatives
- add inefficient terms as negatives
- lower related keyword bids when search-term CPA is too high
- pause exact keywords that spent with no installs
- include guide hygiene checks for duplicate keywords, missing Discovery negatives, Search Match drift, and multi-country drift

### 5. Review And Apply Plans

For spend-affecting optimization, prefer a plan first:

```bash
asa optimize --lookback 14d --out optimize-plan.json
asa plan show optimize-plan.json
asa apply optimize-plan.json --note "Approved after weekly review"
```

Plan actions currently cover:

- add keywords
- add negative keywords
- update keyword bids
- pause keywords
- update campaign daily budgets
- record informational guide checks

Executable plan actions require a reason before they can be saved or applied. Applied plans and decision records are appended locally:

```text
~/.asa-cli/applied-plans.jsonl
~/.asa-cli/decision-log.jsonl
```

Review decision history:

```bash
asa decisions list
asa decisions show <DECISION_ID>
asa decisions export --output decisions.md
```

### 6. Operate Daily Or Weekly

```bash
asa report daily
asa report weekly
asa report weekly --json
asa report weekly --out weekly-report.json
```

Operator reports summarize spend, taps, installs, TTR, CVR, CPA, winners, losers, pacing issues, and next actions.

Budget pacing can also produce a plan:

```bash
asa budget pacing
asa budget pacing --daily
asa budget pacing --month
asa budget pacing --days 7 --out budget-plan.json
asa plan show budget-plan.json
```

Budget pacing can recommend:

- raising daily budget for capped winners
- lowering daily budget for inefficient campaigns
- investigating campaigns with under-delivery and low impression volume

## Rules

Rules let each app define its own operating defaults without hardcoding thresholds into commands.

Generate a starter file:

```bash
asa config rules-template --output asa-rules.json
```

Example:

```json
{
  "currency": "USD",
  "goals": {
    "target_cpa": 5.0,
    "target_roas": null,
    "monthly_budget": 1000.0
  },
  "campaign_strategy": {
    "strategy": "four_campaigns",
    "search_results_only": true,
    "one_country_per_campaign": true,
    "discovery_search_match_enabled": false
  },
  "optimization": {
    "cpa_threshold": 5.0,
    "min_installs": 2,
    "min_spend": 1.0,
    "min_impressions": 10,
    "pause_keyword_min_spend": null,
    "lower_bid_cpa_multiplier": 1.5,
    "raise_bid_cpa_multiplier": 0.8,
    "raise_bid_min_installs": 2
  },
  "bids": {
    "max_bid_change_pct": 25.0,
    "bid_adjustment_pct": 10.0,
    "min_bid": 0.5,
    "max_bid": 3.0
  },
  "reporting": {
    "summary_days": 30,
    "search_terms_days": 14,
    "min_impressions": 10,
    "currency": "USD"
  }
}
```

Use the same file across commands:

```bash
asa optimize --rules asa-rules.json --out plan.json
asa search-terms mine --rules asa-rules.json --out search-term-plan.json
asa report weekly --rules asa-rules.json
asa reports bid-recommendations --rules asa-rules.json --out bid-plan.json
asa budget pacing --rules asa-rules.json --out budget-plan.json
```

Rules can be JSON or YAML. CLI flags still override rule defaults for one-off runs.

## Reporting Commands

```bash
asa report daily
asa report weekly

asa reports summary --days 7
asa reports keywords --sort cpa
asa reports search-terms --winners
asa reports search-terms --negatives
asa reports impression-share --all
asa reports bid-recommendations
asa reports ads
```

For larger exports:

```bash
asa reports custom --days 30
asa reports custom-list
asa reports custom-get <REPORT_ID>
```

Both `asa report ...` and `asa reports ...` are available. The singular group is intended for operator briefs; the plural group keeps the broader reporting commands.

## Budget Commands

```bash
asa budget list
asa budget get <BUDGET_ORDER_ID>
asa budget status --rules asa-rules.json
asa budget pacing --days 7 --out budget-plan.json
asa budget create --name "June 2026" --budget 5000 --start 2026-06-01 --end 2026-06-30 --reason "Fund June scaling plan"
```

Budget status highlights serving and budget problems. Budget pacing turns recent spend quality into plan actions.

## Decision Log

Every serving or spend-affecting workflow should explain why the change exists. Generated plans store action-level reasons, metrics, source, and rule metadata. Direct campaign, ad group, keyword, ad, geo, and budget lifecycle commands also require a reason before mutating live account state.

```bash
asa campaigns pause 123456789 --reason "Duplicate campaign replaced by clean clone"
asa apply budget-plan.json --note "Approved because Category CPA is below target"
asa decisions list
asa decisions show <DECISION_ID>
asa decisions export --output decisions.md
```

For LLM-assisted operations, the expected standard is the same: record the strategic reason, evidence, rules used, expected outcome, and follow-up window in the local decision log.

## Geo, Ads, And Account Tools

```bash
# Geo targeting
asa geo search "Australia"
asa geo show
asa geo set --campaign 123456789 --countries AU,NZ

# Ads and product pages
asa ads list --campaign 123456789
asa ads creatives --campaign 123456789 --ad-group 987654321
asa ads product-pages
asa ads rejections

# Account and app access
asa acl me
asa acl list
asa acl search-apps "My App"
asa acl eligibility <ADAM_ID>
asa acl countries
```

## Multi-App Mode

Add and switch between apps:

```bash
asa config add-app
asa config list-apps
asa config switch noteo
```

Run any command against a specific app:

```bash
asa --app noteo campaigns list --all
asa --app lofto search-terms mine --out lofto-search-plan.json
asa --app lofto budget pacing --days 7
```

## Campaign Strategy

The default strategy is built around Search Results campaigns:

| Type | Purpose | Match |
| --- | --- | --- |
| Brand | Protect your own brand searches | Exact |
| Category | Control high-intent category terms | Exact |
| Competitor | Test competitor app or brand terms | Exact |
| Discovery | Find new terms and test wider intent | Broad / Search Match |

The practical rule is simple: keep high-value exact terms controlled, use Discovery to learn, and avoid bidding against yourself by duplicating the same active keyword intent in multiple places.

## Safety Model

`asa-copilot` treats account changes as operations, not magic.

- spend-affecting recommendations can be saved as plans first
- executable plan actions require a reason before save/apply
- direct campaign, ad group, keyword, ad, geo, and budget mutations capture a reason
- destructive actions require explicit commands
- duplicate keyword errors are handled without failing the whole run
- bid rules can cap aggressive changes
- credentials stay in local config files
- applied plans are recorded locally
- decision records are recorded locally
- JSON output is available for automation and scheduled runs

## Local Checks

```bash
pytest
python -m py_compile $(find asa_cli -name '*.py' -print)
python -m asa_cli.main search-terms mine --help
python -m asa_cli.main report weekly --help
python -m asa_cli.main budget pacing --help
python -m asa_cli.main decisions list --help
```

## License

MIT. See [LICENSE](LICENSE).

Originally forked from `cameronehrlich/apple-search-ads-cli`; `asa-copilot` is evolving as a separate operations-focused CLI.
