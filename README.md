# College Football Matchup Lab

Mobile-friendly FBS matchup dashboard, daily CFBD ingestion, and transparent chronological projection validation. Hosting: GitHub Pages. No paid services or client-side API credentials.

## One-time setup

1. Add your free CFBD key as the repository Actions secret `CFBD_API_KEY`. Never commit it.
2. Settings → Pages → Build and deployment → Source: **GitHub Actions**.
3. Actions → **Refresh data and deploy** → Run workflow.

The workflow runs daily at 10:17 UTC, on code pushes, and manually. GitHub may delay scheduled runs; inactive public repositories can have schedules disabled after 60 days. It preserves the last successful snapshot and fails visibly if ingestion fails. Check the Actions page if the dashboard reports stale data.

Expected URL after successful deployment: https://cadenlawson1-stack.github.io/college-football-matchup-lab/
This URL is not proof of deployment.

## Free-tier budget

Initial API use: five games requests (four past seasons and current season) plus one current advanced-stats request. Normal daily use: two requests, about 62/month. Past seasons use an Actions cache; eviction causes a small history refetch. No per-visitor API requests. No credit card, paid data tier, server, or domain is required. CFBD documents 1,000 free calls/month as of October 23, 2026. Rate limits and endpoint access remain controlled by the provider.

## Data and model

`/games?year=...&seasonType=both` and `/stats/season/advanced?year=...&classification=fbs&excludeGarbageTime=true` are the only provider endpoints. Advanced metrics are unadjusted season-to-date PPA, success, explosiveness, passing/rushing splits, downs, scoring opportunities, havoc and line-yard metrics. They are comparisons, not model inputs in v1. Missing values display as dashes.

The points model uses completed FBS versus FBS games and five-game shrinkage toward 28 points. Prior seasons decay by 65%; home margin advantage is 3 points. Predictions for a historical date are computed before any outcomes from that date are consumed. For the 2026 season, probability scale is fitted on 2024 and tested on 2025. Earlier 2022–2023 games initialize team history. Current-season games are not used to tune that scale or report holdout results.

Validation reports Brier score, log loss, score MAE, accuracy, expected calibration error, and calibration bins. Passing requires at least 200 games in both calibration and holdout, better Brier score than 0.25 and a calibration-year home-rate baseline, score MAE better than the fixed 28-point baseline, and ECE ≤ 0.10. Estimates remain experimental unless every gate passes. One holdout season is an initial check, not comprehensive model validation. No claim of betting edge or advanced-metric-driven projections is made.

## Development

No third-party runtime dependencies. Python 3.10+ for ingestion/tests. Browser-native HTML/CSS/JavaScript for the dashboard.

```
python -m unittest discover -s tests -v
python -m http.server 8080 --directory docs
```

The CFBD secret is available only to the refresh process in Actions. The public snapshot includes team statistics, team model summaries, fixtures, and validation results. It never includes the key. Source: https://collegefootballdata.com. API documentation: https://api.collegefootballdata.com.
