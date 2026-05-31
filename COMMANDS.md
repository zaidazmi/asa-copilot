# Command Reference

Generated from the current CLI help output.

Regenerate with:

```bash
python scripts/generate_command_reference.py
```

## `asa`

```text
Usage: asa [OPTIONS] COMMAND [ARGS]...                                         
                                                                                
 asa-copilot - Apple Search Ads operations CLI.                                 
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --app                 -A      TEXT  App slug to operate on (e.g.,            │
│                                     'stitchit', 'colorcub'). Overrides       │
│                                     active app.                              │
│                                     [env var: ASA_APP]                       │
│                                     [default: None]                          │
│ --format                      TEXT  JSON output format for --json commands:  │
│                                     json, pretty, or compact.                │
│                                     [default: json]                          │
│ --install-completion                Install completion for the current       │
│                                     shell.                                   │
│ --show-completion                   Show completion for the current shell,   │
│                                     to copy it or customize the              │
│                                     installation.                            │
│ --help                              Show this message and exit.              │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ version        Show version information.                                     │
│ help           Show help and quick start guide.                              │
│ apply          Apply a saved change plan and record it in local audit        │
│                history.                                                      │
│ config         Configuration management                                      │
│ campaigns      Campaign management                                           │
│ adgroups       Ad group management                                           │
│ keywords       Keyword management                                            │
│ plan           Review saved change plans                                     │
│ decisions      Decision log and reasoning                                    │
│ reports        Reporting and analytics                                       │
│ report         Reporting and analytics                                       │
│ search-terms   Search-term mining                                            │
│ optimize       Automated campaign optimization                               │
│ budget         Budget order management                                       │
│ geo            Geo targeting and location search                             │
│ ads            Ad variations, creatives, and product pages                   │
│ acl            Access control, user management, and app search               │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## `asa config`

```text
Usage: asa config [OPTIONS] COMMAND [ARGS]...                                  
                                                                                
 Configuration management                                                       
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ setup            Set up API credentials and app configuration.               │
│ show             Display current configuration.                              │
│ rules-template   Write a generic JSON rule-file template.                    │
│ test             Test API connection with current credentials.               │
│ add-app          Add a new app to the multi-app configuration.               │
│ discover-app     Search App Store apps and show adam_id values for           │
│                  configuration.                                              │
│ list-apps        List all configured apps.                                   │
│ switch           Switch the active app.                                      │
│ remove-app       Remove an app from the configuration.                       │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## `asa config discover-app`

```text
Usage: asa config discover-app [OPTIONS] QUERY                                 
                                                                                
 Search App Store apps and show adam_id values for configuration.               
                                                                                
╭─ Arguments ──────────────────────────────────────────────────────────────────╮
│ *    query      TEXT  App Store search query [default: None] [required]      │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --owned    --all                              Only show apps owned by this   │
│                                               org                            │
│                                               [default: owned]               │
│ --limit             INTEGER RANGE [1<=x<=50]  Maximum results [default: 10]  │
│ --json                                        Output app results as JSON     │
│ --help                                        Show this message and exit.    │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## `asa campaigns`

```text
Usage: asa campaigns [OPTIONS] COMMAND [ARGS]...                               
                                                                                
 Campaign management                                                            
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ list     List all campaigns.                                                 │
│ setup    Set up the 4-campaign structure (Brand, Category, Competitor,       │
│          Discovery).                                                         │
│ audit    Audit current campaign structure against Apple's recommendations.   │
│ pause    Pause a campaign or all managed campaigns.                          │
│ enable   Enable a campaign or all managed campaigns.                         │
│ create   Create a new campaign with custom settings.                         │
│ update   Update a campaign's name, budget, lifetime budget, or status.       │
│ clone    Duplicate a campaign (with ad groups, keywords, and negatives).     │
│ delete   Delete a campaign. WARNING: This is irreversible.                   │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## `asa adgroups`

```text
Usage: asa adgroups [OPTIONS] COMMAND [ARGS]...                                
                                                                                
 Ad group management                                                            
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ list     List all ad groups for a campaign.                                  │
│ create   Create a new ad group in a campaign.                                │
│ update   Update an ad group's settings.                                      │
│ pause    Pause an ad group.                                                  │
│ enable   Enable an ad group.                                                 │
│ delete   Delete an ad group. WARNING: This is irreversible.                  │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## `asa keywords`

```text
Usage: asa keywords [OPTIONS] COMMAND [ARGS]...                                
                                                                                
 Keyword management                                                             
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ list               List keywords in a campaign or ad group.                  │
│ add                Add keywords to a campaign with automatic routing.        │
│ add-negatives      Add negative keywords to block unwanted search terms.     │
│ promote            Promote keywords from Discovery to exact match campaigns. │
│ delete             Delete keywords from a campaign.                          │
│ update-bid         Update bid amount for a keyword.                          │
│ pause              Pause a keyword or all active keywords.                   │
│ enable             Enable a paused keyword or all paused keywords.           │
│ research           Research keywords — get Apple's recommendations and       │
│                    search popularity scores.                                 │
│ list-negatives     List negative keywords for a campaign (campaign +         │
│                    ad-group level).                                          │
│ delete-negatives   Delete negative keywords by comma-separated IDs.          │
│ find               Search targeting keywords across a campaign.              │
│ update-bids-bulk   Update all keyword bids in a campaign/ad group at once.   │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## `asa search-terms`

```text
Usage: asa search-terms [OPTIONS] COMMAND [ARGS]...                            
                                                                                
 Search-term mining                                                             
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ mine   Mine Discovery search terms and produce a reviewable change plan.     │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## `asa reports`

```text
Usage: asa reports [OPTIONS] COMMAND [ARGS]...                                 
                                                                                
 Reporting and analytics                                                        
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ daily                 Show a daily operator report with pacing next actions. │
│ weekly                Show a weekly operator report with pacing next         │
│                       actions.                                               │
│ summary               Show performance summary across all campaigns.         │
│ keywords              Show keyword performance report.                       │
│ adgroups              Show ad group performance report.                      │
│ impression-share      Show impression share (Share of Voice) report for      │
│                       keywords.                                              │
│ search-terms          Show search terms report - discover new keywords and   │
│                       negatives.                                             │
│ custom                Create a custom impression share report, poll until    │
│                       complete, and display results.                         │
│ custom-list           List all custom reports.                               │
│ custom-get            Get a specific custom report status and results.       │
│ ads                   Show ad-level performance report.                      │
│ raw                   Fetch a raw campaign report with optional Apple report │
│                       groupBy fields.                                        │
│ bid-recommendations   Show Apple's suggested bid amounts vs current bids for │
│                       keywords.                                              │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## `asa reports raw`

```text
Usage: asa reports raw [OPTIONS]                                               
                                                                                
 Fetch a raw campaign report with optional Apple report groupBy fields.         
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ *  --campaign            -c      INTEGER               Campaign ID           │
│                                                        [default: None]       │
│                                                        [required]            │
│    --days                -d      INTEGER RANGE [x>=1]  Number of days        │
│                                                        [default: 7]          │
│    --start                       TEXT                  Start date            │
│                                                        (YYYY-MM-DD)          │
│                                                        [default: None]       │
│    --end                         TEXT                  End date (YYYY-MM-DD) │
│                                                        [default: None]       │
│    --granularity                 TEXT                  DAILY, WEEKLY,        │
│                                                        MONTHLY               │
│                                                        [default: DAILY]      │
│    --group-by                    TEXT                  Comma-separated Apple │
│                                                        report grouping       │
│                                                        fields, e.g.          │
│                                                        countryOrRegion,devi… │
│                                                        [default: None]       │
│    --return-records-wi…                                Include rows with no  │
│                                                        metrics               │
│    --json                                              Output raw report     │
│                                                        JSON                  │
│    --out                         PATH                  Write raw report JSON │
│                                                        to this path          │
│                                                        [default: None]       │
│    --help                                              Show this message and │
│                                                        exit.                 │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## `asa reports bid-recommendations`

```text
Usage: asa reports bid-recommendations [OPTIONS]                               
                                                                                
 Show Apple's suggested bid amounts vs current bids for keywords.               
 For each campaign and ad group, fetches the keyword report with bid            
 recommendation insights. Displays a color-coded table showing where            
 your bids are below Apple's suggestions.                                       
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --campaign  -c      INTEGER  Campaign ID [default: None]                     │
│ --days      -d      INTEGER  Number of days [default: 14]                    │
│ --all       -a               Show bids for all campaigns                     │
│ --rules             PATH     JSON or YAML rule file overriding app config    │
│                              defaults                                        │
│                              [default: None]                                 │
│ --json                       Output rule recommendations as JSON             │
│ --out               PATH     Write bid/pause recommendations to a plan JSON  │
│                              file                                            │
│                              [default: None]                                 │
│ --help                       Show this message and exit.                     │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## `asa budget`

```text
Usage: asa budget [OPTIONS] COMMAND [ARGS]...                                  
                                                                                
 Budget order management                                                        
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ list     List all budget orders.                                             │
│ get      Show details of a specific budget order.                            │
│ status   Campaign budget health dashboard.                                   │
│ pacing   Analyze budget pace and recommend budget plan actions.              │
│ create   Create a new budget order.                                          │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## `asa geo`

```text
Usage: asa geo [OPTIONS] COMMAND [ARGS]...                                     
                                                                                
 Geo targeting and location search                                              
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ search   Search for geo locations (countries, states, cities).               │
│ show     Show geo targeting for all campaigns.                               │
│ set      Set country targeting for a campaign.                               │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## `asa ads`

```text
Usage: asa ads [OPTIONS] COMMAND [ARGS]...                                     
                                                                                
 Ad variations, creatives, and product pages                                    
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ list            List all ads. Provide campaign + ad group for a specific     │
│                 group, or search across all.                                 │
│ create          Create a new ad in an ad group.                              │
│ delete          Delete an ad. WARNING: This is irreversible.                 │
│ creatives       List creatives or get details for a specific creative.       │
│ product-pages   List custom product pages for an app.                        │
│ rejections      Show product page rejection reasons.                         │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## `asa acl`

```text
Usage: asa acl [OPTIONS] COMMAND [ARGS]...                                     
                                                                                
 Access control, user management, and app search                                
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ list          Show organizations and roles for the current user.             │
│ me            Show current user info.                                        │
│ search-apps   Search for iOS apps on the App Store.                          │
│ eligibility   Check app advertising eligibility.                             │
│ countries     Show supported countries/regions for advertising.              │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## `asa optimize`

```text
Usage: asa optimize [OPTIONS] COMMAND [ARGS]...                                
                                                                                
 Automated campaign optimization                                                
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --days             -d      INTEGER  Days to analyze [default: None]          │
│ --lookback                 TEXT     Lookback window, e.g. 14d. Overrides     │
│                                     --days.                                  │
│                                     [default: None]                          │
│ --cpa-threshold    -c      FLOAT    Max CPA for winners (USD)                │
│                                     [default: None]                          │
│ --min-installs     -i      INTEGER  Min installs to promote [default: None]  │
│ --min-spend        -s      FLOAT    Min spend to consider blocking (USD)     │
│                                     [default: None]                          │
│ --min-impressions          INTEGER  Min impressions to consider a term       │
│                                     [default: None]                          │
│ --exclude          -e      TEXT     Comma-separated terms to exclude from    │
│                                     analysis                                 │
│                                     [default: None]                          │
│ --dry-run          -n               Preview changes without applying         │
│ --auto-approve     -y               Skip confirmation prompts                │
│ --target           -t      TEXT     Target campaign for promotions: brand,   │
│                                     category, competitor                     │
│                                     [default: category]                      │
│ --json                              Output results as JSON (implies          │
│                                     --dry-run)                               │
│ --out                      PATH     Write proposed changes to a plan JSON    │
│                                     file                                     │
│                                     [default: None]                          │
│ --rules                    PATH     JSON or YAML rule file overriding app    │
│                                     config defaults                          │
│                                     [default: None]                          │
│ --help                              Show this message and exit.              │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## `asa plan`

```text
Usage: asa plan [OPTIONS] COMMAND [ARGS]...                                    
                                                                                
 Review saved change plans                                                      
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ show   Show the changes in a saved plan.                                     │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## `asa decisions`

```text
Usage: asa decisions [OPTIONS] COMMAND [ARGS]...                               
                                                                                
 Decision log and reasoning                                                     
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ list     List recent decision records.                                       │
│ show     Show one decision record.                                           │
│ export   Export the local decision log.                                      │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## `asa apply`

```text
Usage: asa apply [OPTIONS] PATH                                                
                                                                                
 Apply a saved change plan and record it in local audit history.                
                                                                                
╭─ Arguments ──────────────────────────────────────────────────────────────────╮
│ *    path      TEXT  Path to a plan JSON file [default: None] [required]     │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --auto-approve  -y            Skip confirmation prompt                       │
│ --json                        Output apply result as JSON                    │
│ --note                  TEXT  Human approval note [default: None]            │
│ --actor                 TEXT  Actor recorded in the decision log             │
│                               [default: cli]                                 │
│ --help                        Show this message and exit.                    │
╰──────────────────────────────────────────────────────────────────────────────╯
```
