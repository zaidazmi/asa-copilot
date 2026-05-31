# asa-copilot

Apple Search Ads operations from the command line.

`asa-copilot` is a practical CLI for indie iOS developers and small growth teams who want to manage Apple Search Ads without living in spreadsheets or clicking through Ads Manager all day. It helps you set up campaign structure, inspect account health, manage keywords, review search-term data, generate change plans, and apply spend-affecting actions with an audit trail.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Apple Ads API v5](https://img.shields.io/badge/Apple%20Ads%20API-v5-black.svg)](https://developer.apple.com/documentation/apple_ads)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

```bash
asa optimize --lookback 14d --rules asa-rules.json --out plan.json
asa plan show plan.json
asa apply plan.json
```

## What It Does

`asa-copilot` is built around an operator workflow:

1. Configure one or more apps.
2. Audit campaign structure and serving status.
3. Mine keywords and search terms.
4. Generate a reviewable plan for spend-affecting changes.
5. Apply approved changes and keep local history.
6. Repeat with configurable rules.

The CLI command is intentionally short:

```bash
asa --help
```

## Highlights

- Multi-app configuration with `asa --app <slug> ...`
- Apple Ads API credential setup and connection testing
- Campaign create, clone, update, pause, enable, audit, and delete
- Keyword routing for brand, category, competitor, and discovery campaigns
- Negative keyword management at campaign and ad group levels
- Search-term reporting for winners and negatives
- Plan / approve / apply flow for optimization changes
- Local audit history for applied plans
- JSON/YAML rule files for thresholds and guardrails
- Bid-change caps and typed optimization defaults
- Budget order and campaign budget health views
- Geo targeting inspection and updates
- Ad, creative, product page, rejection, ACL, and app eligibility commands

## Install

```bash
git clone https://github.com/zaidazmi/asa-copilot.git
cd asa-copilot
pip install -e .
asa --help
```

You can also run through `uv` if you prefer:

```bash
uv run asa --help
```

## Configure

Start with your Apple Ads API credentials and app metadata:

```bash
asa config setup
asa config test
asa config show
```

Credentials and app config are stored locally:

```text
~/.asa-cli/
|-- credentials.json
|-- config.json
|-- rules.json
`-- applied-plans.jsonl
```

`credentials.json` contains sensitive API credentials. Keep it local.

### Apple Ads API Credentials

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

Upload only the public key to Apple. Use the private key path in `asa config setup`.

## Core Workflow

### 1. Audit

```bash
asa campaigns list --all
asa campaigns audit
asa budget status
```

Use this to see what exists, what is paused or on hold, and whether campaigns match the expected structure.

### 2. Manage Campaigns

```bash
asa campaigns setup --countries US --budget 50 --dry-run
asa campaigns setup --countries US --budget 50

asa campaigns create "MyApp - Category - Exact - US" --countries US --budget 20 --status PAUSED
asa campaigns update 123456789 --budget 15
asa campaigns pause 123456789
asa campaigns enable 123456789
```

Campaign operations are explicit by default. Use IDs when changing live objects.

### 3. Manage Keywords

```bash
asa keywords add "ai note taker,voice notes" --type category
asa keywords add "competitor app,another app" --type competitor

asa keywords list --campaign 123456789
asa keywords find "notes"
asa keywords update-bids-bulk --campaign 123456789 --bid 1.25
```

Keyword routing understands the campaign type:

- brand terms go to brand exact campaigns
- category terms go to category exact campaigns
- competitor terms go to competitor exact campaigns
- discovery receives broad coverage and/or negatives where appropriate

### 4. Mine Search Terms

```bash
asa reports search-terms --campaign 123456789 --days 14
asa reports search-terms --winners
asa reports search-terms --negatives
```

Search-term reports help identify:

- terms worth promoting into exact campaigns
- terms spending without installs
- queries that should be blocked as negatives

### 5. Plan, Review, Apply

For spend-affecting optimization, prefer a plan first:

```bash
asa optimize --lookback 14d --out plan.json
asa plan show plan.json
asa apply plan.json
```

`asa optimize` can still run interactively, but plans are the safer path. They make proposed changes visible before anything touches the account.

Plan actions currently cover:

- add keywords
- add negative keywords
- update keyword bids
- pause keywords
- update campaign budgets
- creative mapping checks

Applied plans are appended to:

```text
~/.asa-cli/applied-plans.jsonl
```

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
    "min_impressions": 10
  },
  "bids": {
    "max_bid_change_pct": 25.0,
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
asa reports summary --rules asa-rules.json
asa reports search-terms --rules asa-rules.json
asa budget status --rules asa-rules.json
```

Rules can be JSON or YAML. CLI flags still override rule defaults for one-off runs.

## Reporting

```bash
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

## Budgets

```bash
asa budget list
asa budget get <BUDGET_ORDER_ID>
asa budget status --rules asa-rules.json
asa budget create --name "June 2026" --budget 5000 --start 2026-06-01 --end 2026-06-30
```

Budget status highlights serving and budget problems across campaigns.

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
asa --app lofto optimize --out lofto-plan.json
```

## Campaign Strategy

The default strategy is built around Search Results campaigns:

| Type | Purpose | Match |
| --- | --- | --- |
| Brand | protect your own brand searches | exact |
| Category | controlled high-intent category terms | exact |
| Competitor | competitor app or brand terms | exact |
| Discovery | find new terms and test wider intent | broad / Search Match |

The practical rule is simple: keep high-value exact terms controlled, use discovery to learn, and avoid bidding against yourself by duplicating the same active keyword intent in multiple places.

## Safety Model

`asa-copilot` treats account changes as operations, not magic.

- destructive actions require explicit commands
- optimization can emit a reviewable plan before applying
- duplicate keyword errors are handled without failing the whole run
- credentials stay in local config files
- applied plans are recorded locally
- bid rules can cap aggressive changes

## Development

```bash
pip install -e ".[dev]"
pytest
```

Useful local checks:

```bash
asa --help
asa config rules-template --output /tmp/asa-rules.json --force
asa optimize --help
```

## License

MIT. See [LICENSE](LICENSE).

Originally forked from `cameronehrlich/apple-search-ads-cli`; `asa-copilot` is evolving as a separate operations-focused CLI.
