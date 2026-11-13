@echo off
rem Daily forward paper run, then publish results/paper to the paper-ledger branch.
rem Round 3 (review E-3): the record no longer goes to main. This runs in a separate worktree
rem on paper-ledger, made once with
rem   git -C C:\Work\Claude\AgenticTrader worktree add C:\Work\Claude\AgenticTrader-paper paper-ledger
rem and uses the .venv of the main checkout.
cd /d C:\Work\Claude\AgenticTrader-paper
rem Round 2 (review D13): pull BEFORE the session, so it extends the published ledger, not a
rem stale local copy; a pull that cannot fast-forward stops the run (a person must look).
git pull -q --ff-only origin paper-ledger >> results\paper\cron.log 2>&1
if errorlevel 1 exit /b 1
rem Bring the code up to main. Main no longer changes results/paper, so this cannot conflict
rem with the record; a failed merge stops the run.
git fetch -q origin main >> results\paper\cron.log 2>&1
git merge -q --no-edit origin/main >> results\paper\cron.log 2>&1
if errorlevel 1 exit /b 1
C:\Work\Claude\AgenticTrader\.venv\Scripts\python.exe scripts\paper_trade_v09.py >> results\paper\cron.log 2>&1
if errorlevel 1 exit /b 1
C:\Work\Claude\AgenticTrader\.venv\Scripts\python.exe scripts\paper_mask_paths.py >> results\paper\cron.log 2>&1
rem append-only check against the commit the session started from (review D6)
C:\Work\Claude\AgenticTrader\.venv\Scripts\python.exe scripts\paper_ledger_check.py --base HEAD >> results\paper\cron.log 2>&1
if errorlevel 1 exit /b 1
rem Fallback path; the primary runner is .github/workflows/paper.yml (run one, not both).
C:\Work\Claude\AgenticTrader\.venv\Scripts\python.exe scripts\paper_ops.py commit --message "paper: daily record [skip ci]" >> results\paper\cron.log 2>&1
rem push with rebase-and-retry on a lost race (5 pushes, 5/10/20/40 s backoff)
C:\Work\Claude\AgenticTrader\.venv\Scripts\python.exe scripts\paper_ops.py push --branch paper-ledger --attempts 5 --backoff 5 >> results\paper\cron.log 2>&1
