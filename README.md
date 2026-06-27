# daily-streak-pipeline

ETL pipeline that reads from Supabase, runs the three-lens streak model and alignment engine across Core 6 markets, writes signals to `flagged_opportunities`, and broadcasts via Telegram (shadow mode by default).

## Architecture

```
Supabase (streak DB)
    └── streak_scanner.py   — three-lens streak model (venue, overall, divergence)
    └── correlation_checker.py — contradiction removal (greedy, weakest leg first)
    └── pipeline.py         — orchestrates scan → check → write → notify
    └── telegram_notifier.py — shadow mode: logs but does not send until SHADOW_MODE=false
```

## Setup

```bash
cp .env.example .env
# Fill in DATABASE_URL (session pooler), API_FOOTBALL_KEY, TELEGRAM_*
pip install -r requirements.txt
```

## Connection note

`DATABASE_URL` **must** use the session pooler format:
```
postgresql://postgres.[ref]:[password]@aws-1-eu-north-1.pooler.supabase.com:5432/postgres
```
Do NOT use the `db.*.supabase.co` direct format — it requires IPv6 and fails on most networks.

## Run

```bash
python -c "from src.db import test_connection; test_connection()"
python -m src.pipeline
```

## Signal tiers

| Tier | Min streak | Markets |
|------|-----------|---------|
| HIGH_SIGNAL | 5/5 | All tiers |
| MODERATE_SIGNAL | 4/5 | Full + Semi |
| TRACKING | 3/5 | Tracked, not broadcast |

## Shadow mode

`SHADOW_MODE=true` (default) — all signals are written to `flagged_opportunities` and logged, but no Telegram messages are sent. Set `SHADOW_MODE=false` to enable live broadcasts.

## Tests

```bash
pytest tests/ -v
```
