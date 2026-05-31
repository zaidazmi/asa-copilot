<div align="center">

```
 █████╗ ███████╗ █████╗        ██████╗ ██████╗ ██████╗ ██╗██╗      ██████╗ ████████╗
██╔══██╗██╔════╝██╔══██╗      ██╔════╝██╔═══██╗██╔══██╗██║██║     ██╔═══██╗╚══██╔══╝
███████║███████╗███████║█████╗██║     ██║   ██║██████╔╝██║██║     ██║   ██║   ██║   
██╔══██║╚════██║██╔══██║╚════╝██║     ██║   ██║██╔═══╝ ██║██║     ██║   ██║   ██║   
██║  ██║███████║██║  ██║      ╚██████╗╚██████╔╝██║     ██║███████╗╚██████╔╝   ██║   
╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝       ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚══════╝ ╚═════╝    ╚═╝   
```

**A safer Apple Search Ads operations CLI for app developers.**

Pull account data, find waste, generate reviewable plans, apply only what you approve, and keep a reason log for every spend-affecting change.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Apple Ads API v5](https://img.shields.io/badge/Apple%20Ads%20API-v5-000000?style=flat-square&logo=apple&logoColor=white)](https://developer.apple.com/documentation/apple_ads)
[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)](LICENSE)

</div>

```bash
asa search-terms mine --lookback 14d --out plan.json
asa plan show plan.json
asa apply plan.json --note "Approved after weekly review"
```

---

## Why asa-copilot

Apple Ads Manager is good for checking your account. It is slower for repeatable operations: auditing campaign structure, finding bad search terms, moving winners into exact match, updating bids, watching budget pace, and remembering why a change was made.

`asa-copilot` turns Apple Search Ads work into an operator loop:

```text
inspect data -> apply rules -> review plan -> approve changes -> log decisions
```

The CLI is built for indie iOS developers, app studios, and small growth teams that want more control than the dashboard gives, without building a full internal ads platform.

---

## What You Can Do

| Job | Useful commands |
|---|---|
| Audit campaign structure | `asa campaigns audit`, `asa campaigns list --all --bids` |
| Manage multiple apps | `asa config discover-app`, `asa config add-app`, `asa --app <slug> ...` |
| Mine search terms | `asa reports search-terms`, `asa search-terms mine --out plan.json` |
| Promote winners | `asa keywords promote`, `asa apply plan.json` |
| Reduce wasted spend | `asa keywords add-negatives`, generated negative-keyword plans |
| Update bids safely | `asa reports bid-recommendations`, `asa keywords update-bids-bulk` |
| Watch budget pace | `asa budget status`, `asa budget pacing --out budget-plan.json` |
| Review performance | `asa report daily`, `asa report weekly`, `asa reports summary` |
| Export/report raw data | `asa reports raw --group-by ... --json`, `--format compact` |
| Keep an audit trail | `asa decisions list`, `asa decisions export` |

Core features:

- Reviewable JSON plans before applying optimization changes
- Required reasons for campaign, ad group, keyword, bid, budget, pause, and enable actions
- Local decision log with source, reason, metrics, rules, and result
- Multi-app scoping by Apple App ID / `adamId`
- Search-term mining for winners, negatives, bid reductions, and weak exact keywords
- Guide hygiene checks for duplicate intent, missing Discovery negatives, Search Match drift, and multi-country campaign issues
- Rule files for CPA thresholds, bid caps, reporting defaults, and optimization behavior
- JSON output for automation, including compact JSON for scripts

---

## Install

Current install from GitHub:

```bash
pipx install git+https://github.com/zaidazmi/asa-copilot.git
```

Or for local development:

```bash
git clone https://github.com/zaidazmi/asa-copilot.git
cd asa-copilot
pip install -e ".[dev]"
pytest
```

The terminal command is:

```bash
asa --help
```

---

## Configure

Start with the guided setup:

```bash
asa config setup
asa config test
asa config show
```

To find an app's Apple App ID before adding it:

```bash
asa config discover-app "Your App Name"
asa config add-app
asa config list-apps
asa config switch myapp
```

Local state is stored outside the repo:

```text
~/.asa-cli/
├── credentials.json      # Apple Ads API credentials
├── config.json           # App configs and defaults
├── rules.json            # Optional global rule overrides
├── applied-plans.jsonl   # Applied plan history
└── decision-log.jsonl    # Reasons behind changes
```

### Apple Ads API Credentials

In Apple Ads, go to Account Settings -> API. Create API credentials, upload your public key, then collect:

- Organization ID
- Client ID
- Team ID
- Key ID
- Private key PEM path

Generate a key pair:

```bash
openssl ecparam -genkey -name prime256v1 -noout -out apple-ads-private-key.pem
openssl ec -in apple-ads-private-key.pem -pubout -out apple-ads-public-key.pem
```

Upload only the public key to Apple. Use the private key path during `asa config setup`.

For CI, scheduled jobs, or ephemeral shells, credentials can come from environment variables:

```bash
export ASA_ORG_ID=123456789
export ASA_CLIENT_ID=SEARCHADS.xxxxx
export ASA_TEAM_ID=SEARCHADS.xxxxx
export ASA_KEY_ID=xxxxx
export ASA_PRIVATE_KEY_PATH=/secure/apple-ads-private-key.pem
```

`APPLE_ADS_*` aliases are also supported. Environment credentials take precedence over `~/.asa-cli/credentials.json`.

---

## Daily Workflow

### 1. Inspect The Account

```bash
asa campaigns list --all --bids
asa campaigns audit
asa budget status
asa report weekly
```

Use this to check what is running, whether campaign structure still matches your intended setup, and where spend is going.

### 2. Review Search Terms

```bash
asa reports search-terms --campaign 123456789 --days 14
asa reports search-terms --winners
asa reports search-terms --negatives
```

Use this to spot converting terms, irrelevant terms, high-spend/no-install terms, and terms worth moving out of Discovery.

### 3. Generate A Plan

```bash
asa search-terms mine --lookback 14d --out search-term-plan.json
asa optimize --lookback 14d --out optimize-plan.json
asa budget pacing --days 7 --out budget-plan.json
```

Plans can include keyword promotions, negative keywords, bid changes, budget changes, keyword pauses, and informational guide hygiene checks.

### 4. Review And Apply

```bash
asa plan show search-term-plan.json
asa apply search-term-plan.json --note "Approved after checking CPA and search intent"
```

`apply` records what happened locally so you can inspect the change later.

### 5. Check The Decision Log

```bash
asa decisions list
asa decisions show <DECISION_ID>
asa decisions export --output decisions.md
```

This is useful when you want to answer: "Why did we pause this?", "Why did this bid change?", or "What did the optimizer do last week?"

---

## Campaign And Keyword Operations

Create or update campaigns:

```bash
asa campaigns setup --countries US --budget 50 --dry-run
asa campaigns setup --countries US --budget 50 \
  --reason "Launch tested Search Results structure"

asa campaigns create "MyApp - Category - Exact - US" --countries US --budget 20 --status PAUSED \
  --reason "Test category exact demand"

asa campaigns update 123456789 --budget 15 \
  --reason "Reduce spend while CPA is above target"

asa campaigns pause 123456789 \
  --reason "Poor CPA after 14 day test"
```

Add and manage keywords:

```bash
asa keywords add "ai note taker,voice notes" --type category \
  --reason "Expand exact coverage for converting note-taking intent"

asa keywords add-negatives "free games,testflight" --all \
  --reason "Block irrelevant traffic seen in search terms"

asa keywords find "notes"
asa keywords list --campaign 123456789
asa keywords update-bids-bulk --campaign 123456789 --bid 1.25 \
  --reason "Normalize bids after CPA review"
```

Keyword routing follows the standard structure: brand, category, and competitor terms go to exact campaigns; Discovery is used to learn new intent.

---

## Campaign Structure

| Type | Intent | Typical match |
|---|---|---|
| Brand | Your app or company name | Exact |
| Category | High-intent generic searches | Exact |
| Competitor | Competitor app or brand searches | Exact |
| Discovery | Search-term mining and expansion | Broad / Search Match |

The CLI helps you avoid common ASA problems:

- Duplicating the same active keyword intent across campaigns
- Letting Discovery spend without adding negatives
- Mixing countries in campaigns you intended to compare separately
- Leaving campaigns running without knowing why they were changed
- Making bid changes with no guardrails or audit trail

---

## Rules And Guardrails

Create a rule template:

```bash
asa config rules-template --output asa-rules.json
```

Example:

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
    "pause_keyword_min_spend": 6.0,
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

Use rules with planning commands:

```bash
asa optimize --rules asa-rules.json --out plan.json
asa search-terms mine --rules asa-rules.json --out search-term-plan.json
asa budget pacing --rules asa-rules.json --out budget-plan.json
```

Rules can be JSON or YAML. CLI flags can override rule defaults for one-off analysis.

---

## Reporting And Automation

Human-readable reports:

```bash
asa report daily
asa report weekly
asa reports summary --days 7
asa reports keywords --sort cpa
asa reports impression-share --all
asa reports bid-recommendations --rules asa-rules.json
asa reports ads
```

Raw grouped reports for scripts and deeper analysis:

```bash
asa reports raw --campaign 123456789 --group-by countryOrRegion,deviceClass --json
asa --format compact reports raw --campaign 123456789 --json
```

Async custom reports:

```bash
asa reports custom --days 30
asa reports custom-list
asa reports custom-get <REPORT_ID>
```

JSON error responses are consistent on JSON-capable command paths, which makes scheduled jobs easier to monitor.

---

## Multi-App Usage

```bash
asa config discover-app "My App"
asa config add-app
asa config list-apps
asa config switch myapp

asa --app myapp campaigns list --all
asa --app secondapp search-terms mine --out secondapp-plan.json
```

Saved plans include the target app ID, and apply refuses wrong-app plans. `--app` accepts the stored slug or a unique normalized fragment of the app name.

---

## Safety Model

- Recommendations are saved into plans before spend-affecting changes are applied
- Executable plan actions require a reason
- Direct campaign, ad group, keyword, bid, budget, pause, and enable commands require a reason
- Applied plans are stored in `~/.asa-cli/applied-plans.jsonl`
- Manual and plan-applied decisions are stored in `~/.asa-cli/decision-log.jsonl`
- Bid changes can be capped by percentage and min/max bid rules
- Credentials and account-specific files stay outside the repository
- JSON output is available for automation and scheduled runs

---

## Command Reference

See [COMMANDS.md](COMMANDS.md) for generated CLI help.

Regenerate it after command changes:

```bash
python scripts/generate_command_reference.py
```

---

## Development Checks

```bash
pytest
python -m compileall asa_cli scripts
python scripts/generate_command_reference.py
```

---

## License

MIT. See [LICENSE](LICENSE).

Originally forked from `cameronehrlich/apple-search-ads-cli`; developed as a separate operations-focused CLI.
