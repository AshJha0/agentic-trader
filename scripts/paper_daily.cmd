@echo off
rem Daily forward paper run, then publish results/paper to main (owner decision 2026-11-07).
cd /d C:\Work\Claude\AgenticTrader
rem Round 2 (review D13): pull BEFORE the session, so it extends the published ledger, not a
rem stale local copy; a pull that cannot fast-forward stops the run (a person must look).
git pull -q --ff-only origin main >> results\paper\cron.log 2>&1
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe scripts\paper_trade_v09.py >> results\paper\cron.log 2>&1
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe scripts\paper_mask_paths.py >> results\paper\cron.log 2>&1
rem append-only check against the commit the session started from (review D6)
.venv\Scripts\python.exe scripts\paper_ledger_check.py --base HEAD >> results\paper\cron.log 2>&1
if errorlevel 1 exit /b 1
rem Fallback path; the primary runner is .github/workflows/paper.yml (run one, not both).
.venv\Scripts\python.exe scripts\paper_ops.py commit --message "paper: daily record [skip ci]" >> results\paper\cron.log 2>&1
rem push with rebase-and-retry on a lost race (5 pushes, 5/10/20/40 s backoff)
.venv\Scripts\python.exe scripts\paper_ops.py push --attempts 5 --backoff 5 >> results\paper\cron.log 2>&1
