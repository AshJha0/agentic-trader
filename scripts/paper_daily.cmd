@echo off
rem Daily forward paper run, then publish results/paper to main (owner decision 2026-11-07).
cd /d C:\Work\Claude\AgenticTrader
.venv\Scripts\python.exe scripts\paper_trade_v09.py >> results\paper\cron.log 2>&1
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe scripts\paper_mask_paths.py >> results\paper\cron.log 2>&1
git pull -q --ff-only origin main >> results\paper\cron.log 2>&1
git add results/paper/ledger.csv results/paper/ledger_recomputed.csv results/paper/revisions.csv results/paper/runs.jsonl results/paper/summary.md
git diff --cached --quiet && exit /b 0
git commit -q -m "paper: daily record [skip ci]" >> results\paper\cron.log 2>&1
git push -q origin main >> results\paper\cron.log 2>&1
