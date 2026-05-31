<div align="center">

```
 █████╗ ███████╗ █████╗        ██████╗ ██████╗ ██████╗ ██╗██╗      ██████╗ ████████╗
██╔══██╗██╔════╝██╔══██╗      ██╔════╝██╔═══██╗██╔══██╗██║██║     ██╔═══██╗╚══██╔══╝
███████║███████╗███████║█████╗██║     ██║   ██║██████╔╝██║██║     ██║   ██║   ██║   
██╔══██║╚════██║██╔══██║╚════╝██║     ██║   ██║██╔═══╝ ██║██║     ██║   ██║   ██║   
██║  ██║███████║██║  ██║      ╚██████╗╚██████╔╝██║     ██║███████╗╚██████╔╝   ██║   
╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝       ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚══════╝ ╚═════╝    ╚═╝   
```

**Apple Search Ads operations from the terminal.**

*Pull data. Apply rules. Review a plan. Apply only what you approve.*

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Apple Ads API v5](https://img.shields.io/badge/Apple%20Ads%20API-v5-000000?style=flat-square&logo=apple&logoColor=white)](https://developer.apple.com/documentation/apple_ads)
[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)](LICENSE)

</div>

```bash
$ asa search-terms mine --lookback 14d --out plan.json
$ asa plan show plan.json
$ asa apply plan.json
```

---

## Why

Apple Ads Manager is fine for inspection. It's tedious for operations. Auditing campaign structure, finding wasted search terms, keeping bids in line — these tasks compound quickly across multiple apps.

`asa-copilot` wraps them in an operator loop:

```
pull data → apply rules → review plan → apply → log decision
```

Nothing touches your account without going through a reviewable JSON plan first. Every spend-affecting action requires a reason. Everything applied gets recorded locally.

---

## Features

| Area | What it does |
|---|---|
| Plan / apply | Save proposed changes to JSON, review, then apply |
| Decision log | Require reasons for all spend mutations, stored in a local JSONL log |
| Search-term mining | Promote winners, block losers, protect Discovery with negatives |
| Guide hygiene | Catch duplicate keywords, missing Discovery negatives, Search Match drift |
| Optimization rules | Raise/lower bids, pause poor keywords, add negatives — all configurable |
| Operator reports | Daily and weekly briefs with spend, installs, CPA, and next actions |
| Budget pacing | Flag capped winners, cut inefficient campaigns |
| Campaign tools | Create, clone, update, pause, enable, audit |
| Keyword tools | Add, route, promote, bid-update, manage negatives |
| Multi-app | Manage multiple apps with `--app <slug>`; plans and campaign IDs are scoped by app `adamId` |

---

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

---

## Configure

```bash
asa config setup
asa config test
asa config show
```

Local state lives in `~/.asa-cli/`:

```
~/.asa-cli/
├── credentials.json      # Apple Ads API credentials (keep out of git)
├── config.json           # App configurations
├── rules.json            # Optimization thresholds (optional override)
├── applied-plans.jsonl   # Audit log of applied plans
└── decision-log.jsonl    # Reasons behind every change
```

The repository does not require app-specific files. Configure your own iOS apps with `asa config setup` or `asa config add-app`; credentials, app IDs, campaign IDs, and decision logs stay in local `~/.asa-cli/` files outside git.

### API credentials

In Apple Ads: Account Settings → API. Create an API user, upload your public key, and collect the org ID, client ID, team ID, key ID, and private key path.

Generate an EC key pair:

```bash
openssl ecparam -genkey -name prime256v1 -noout -out apple-ads-private-key.pem
openssl ec -in apple-ads-private-key.pem -pubout -out apple-ads-public-key.pem
```

Upload only the public key. Use the private key path during `asa config setup`.

---

## Workflow

### 1. Inspect the account

```bash
asa campaigns list --all
asa campaigns audit
asa budget status
asa report weekly
```

### 2. Manage campaigns

```bash
asa campaigns setup --countries US --budget 50 --dry-run
asa campaigns setup --countries US --budget 50 --reason "Launch tested Search Results structure"

asa campaigns create "MyApp - Category - Exact - US" --countries US --budget 20 --status PAUSED \
  --reason "Test category exact demand"
asa campaigns update 123456789 --budget 15 --reason "Reduce spend while CPA is above target"
asa campaigns pause 123456789 --reason "Poor CPA after 14 day test"
```

### 3. Manage keywords

```bash
asa keywords add "ai note taker,voice notes" --type category \
  --reason "Expand exact coverage for converting note-taking intent"
asa keywords add-negatives "free games,testflight" --all \
  --reason "Block irrelevant traffic seen in search terms"

asa keywords list --campaign 123456789
asa keywords find "notes"
asa keywords update-bids-bulk --campaign 123456789 --bid 1.25 \
  --reason "Normalize bids after CPA review"
```

Keyword routing follows the standard 4-campaign structure: brand, category, and competitor terms go to their respective exact campaigns; everything else goes to Discovery.

### 4. Mine search terms

```bash
# Inspect raw data
asa reports search-terms --campaign 123456789 --days 14
asa reports search-terms --winners
asa reports search-terms --negatives

# Generate a plan
asa search-terms mine --lookback 14d --out search-term-plan.json
asa plan show search-term-plan.json
```

Mining can promote winners into exact campaigns, add them as Discovery negatives, block inefficient terms, lower bids where CPA is high, and pause exact keywords that spent with zero installs.

### 5. Review and apply plans

```bash
asa optimize --lookback 14d --out optimize-plan.json
asa plan show optimize-plan.json
asa apply optimize-plan.json --note "Approved after weekly review"
```

Plan actions cover: add keywords, add negatives, update bids, pause keywords, update budgets, and informational guide checks. Every executable action requires a reason before it can be saved or applied.

### 6. Daily and weekly operation

```bash
asa report daily
asa report weekly
asa budget pacing --days 7 --out budget-plan.json
asa plan show budget-plan.json
```

---

## Rules

Define operating defaults per app without hardcoding thresholds into commands.

```bash
asa config rules-template --output asa-rules.json
```

```json
{
  "currency": "USD",
  "goals": {
    "target_cpa": 5.0,
    "monthly_budget": 1000.0
  },
  "optimization": {
    "cpa_threshold": 5.0,
    "min_installs": 2,
    "min_spend": 1.0,
    "lower_bid_cpa_multiplier": 1.5,
    "raise_bid_cpa_multiplier": 0.8
  },
  "bids": {
    "max_bid_change_pct": 25.0,
    "bid_adjustment_pct": 10.0,
    "min_bid": 0.5,
    "max_bid": 3.0
  }
}
```

Use the same file across commands:

```bash
asa optimize --rules asa-rules.json --out plan.json
asa search-terms mine --rules asa-rules.json --out search-term-plan.json
asa budget pacing --rules asa-rules.json --out budget-plan.json
```

Rules can be JSON or YAML. CLI flags override rule defaults for one-off runs.

---

## Reporting

```bash
asa report daily
asa report weekly

asa reports summary --days 7
asa reports keywords --sort cpa
asa reports search-terms --winners
asa reports impression-share --all
asa reports bid-recommendations --rules asa-rules.json
asa reports ads

# Async exports
asa reports custom --days 30
asa reports custom-list
asa reports custom-get <REPORT_ID>
```

---

## Decision log

```bash
asa decisions list
asa decisions show <DECISION_ID>
asa decisions export --output decisions.md
```

Every spend-affecting change records the reason, metrics, source, and rule metadata. Plans store this at the action level. Direct mutations (campaigns, keywords, budgets) require a reason via `--reason` or an interactive prompt.

---

## Campaign structure

| Type | Intent | Match type |
|---|---|---|
| Brand | Own brand searches | Exact |
| Category | High-intent category terms | Exact |
| Competitor | Competitor app or brand terms | Exact |
| Discovery | New terms, wide intent | Broad / Search Match |

Keep high-value exact terms controlled, use Discovery to learn, and avoid bidding against yourself by duplicating active keyword intent across campaigns.

---

## Safety model

- Spend-affecting recommendations go into a plan before anything runs
- Saved plans record the target app ID and apply refuses wrong-app plans
- Executable plan actions require a reason before save or apply
- Direct campaign, keyword, and budget mutations capture a reason
- Bid rules cap aggressive changes
- Credentials stay in local config files
- Applied plans and decision records are stored locally
- JSON output is available for automation and scheduled runs

---

## Multi-app

```bash
asa config add-app
asa config list-apps
asa config switch myapp

asa --app myapp campaigns list --all
asa --app secondapp search-terms mine --out secondapp-plan.json
```

`--app` accepts the stored slug or a unique normalized fragment of the app name, so short selectors like `myapp` and `secondapp` work when they match only one configured app.

---

## Local checks

```bash
pytest
python -m py_compile $(find asa_cli -name '*.py' -print)
asa search-terms mine --help
asa report weekly --help
asa budget pacing --help
```

---

## License

MIT. See [LICENSE](LICENSE).

Originally forked from `cameronehrlich/apple-search-ads-cli`; developed as a separate operations-focused CLI.
