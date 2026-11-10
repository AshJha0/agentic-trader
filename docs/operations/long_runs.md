# Running the local-model study queue on a laptop

The local-model studies (the P2 study cells, the red-team v2 passes) take days of CPU, not
minutes. They run on one Windows laptop against a local Ollama server, with no paid API.
This page says how that queue is launched, how it survives interruptions, and how to restart
it. It describes practice, not a guarantee: a laptop is not a server, and every run here has
to assume it will be killed at some point.

Paths are written as `<repo>` (the checkout the queue runs from) and `<venv>` (its virtual
environment, usually `<repo>\.venv`). Use a separate checkout for long runs, not the one you
edit in, so a branch switch or a rebuild does not change the code under a running job.

## 1. Launch detached, not from a terminal

**Plain idea.** A job started from a terminal or an editor's tool runner belongs to that
process. Close the window, press Ctrl-C in it, or hit the tool's time limit, and the job dies
with it. A multi-day run has to belong to nothing you are likely to close.

**Specifics.** Each job is a small `.cmd` file that sets the environment and runs one
command, with its output redirected to a log:

```
@echo off
cd /d <repo>
set PYTHONPATH=.
<venv>\Scripts\python.exe -m agentic_trader.agentic.redteam_v2 --model qwen2.5:7b-instruct ^
    --modes json --analysts news,sentiment --no-end-to-end ^
    --out results\redteam_v2\analyst.jsonl > results\redteam_v2\analyst.log 2>&1
```

It is started through WMI, which creates the process outside the calling shell, so closing
the shell does not kill it:

```powershell
Invoke-CimMethod -ClassName Win32_Process -MethodName Create `
    -Arguments @{ CommandLine = 'cmd.exe /c "<repo>\runs\job.cmd"' }
```

The call returns a `ProcessId`; write it down with the start time. Two details that have
cost runs before:

- `.cmd` files must have CRLF line endings. With LF only, `cmd.exe` can misread lines and
  the job fails or runs something other than what the file says.
- Do not start a `.cmd` in the background from a Bash-style tool (`cmd //c job.cmd &`): the
  tool's Ctrl-C when it finishes reaches the job. Use the WMI launcher.

## 2. Chains, `done_*` markers and resume

**Plain idea.** The queue is a chain: one `.cmd` runs several jobs in order. Each finished
job leaves a marker file, and on restart the chain skips any job whose marker exists. Inside
a job the study scripts resume on their own: they append one JSON row per finished unit and
skip units whose key is already in the output file.

**Specifics.**

```
if exist runs\done_analyst goto e2e
<venv>\Scripts\python.exe -m agentic_trader.agentic.redteam_v2 ... --out results\redteam_v2\analyst.jsonl > ... 2>&1
if errorlevel 1 exit /b 1
type nul > runs\done_analyst
:e2e
if exist runs\done_e2e goto end
...
:end
```

- Write the marker only after the job exits with code 0. A crashed job must not be marked
  done; the next start resumes it from its last row.
- Relaunching the same chain is always safe: finished jobs are skipped by marker, finished
  units by key. Do not delete an output `.jsonl` to "start clean" unless you mean to throw
  the rows away.
- `redteam_v2` writes `<out>.design.json` and refuses to append to an output written with
  different design flags (per-category N, seed, end to end on or off). If it refuses, the
  command line changed; fix the command, not the guard.
- `scripts/llm_study.py` checks the served model digest before the first new row and every
  25 rows. If the model behind the tag changed (an `ollama pull` mid-run), it stops with
  `ModelSwapped` and keeps the rows already written. Rows from two digests are two studies.

## 3. What dies on shutdown or reboot, and how to restart

Everything in the queue dies: the chain `.cmd`, the Python job and the Ollama server.
Nothing restarts itself. Sleep and hibernation stop progress too, and a job that was waiting
on a reply when the machine slept can wake up to a dead connection. With Fast Startup
enabled, Windows "Shut down" is closer to hibernation than to a reboot; use a real restart
(`shutdown /r /t 0`) when you need a clean state.

Restart in this order:

1. **Start Ollama**: the Ollama app, or `ollama serve` from its own detached `.cmd`.
2. **Check that it answers**, not only that the process exists:

   ```powershell
   (Invoke-RestMethod http://127.0.0.1:11434/api/tags -TimeoutSec 10).models | Select-Object name, digest
   ```

   The study's model (for example `qwen2.5:7b-instruct`) must be listed with the digest the
   study recorded. A different digest is a different model; see section 2.
3. **Relaunch each chain** with the WMI launcher, unchanged. The markers and row keys do the
   rest.
4. **Read the logs** a few minutes later: each should show new rows, not a start-up followed
   by an exit.

## 4. Spotting a hung Ollama

**Plain idea.** The failure that wastes the most time is a hang, not a crash. The Ollama
process is alive, so nothing looks wrong in Task Manager, but the port no longer answers,
and the job sits on each request until the client gives up.

**Specifics.** Look at three things together:

| Check | Healthy | Hung |
|---|---|---|
| `Get-Process ollama*` | present | present |
| `Invoke-RestMethod http://127.0.0.1:11434/api/tags -TimeoutSec 10` | returns the model list | times out or is refused |
| last line of the job log | changes every few minutes | unchanged for much longer than one call |

When the process is alive and the port is dead: stop the chain, stop every `ollama` process,
start Ollama again, confirm `/api/tags` answers, and relaunch the chain. Resume keeps the
finished rows; at most the unit in flight is repeated.

### Is a Python job alive? Check the worker, not the launcher

On Windows, `<venv>\Scripts\python.exe` is a small launcher. It starts the real interpreter as
a child process and then waits, using no CPU. A job whose launcher shows 0 CPU may be working
normally. Before calling a job hung, find the child (`Get-CimInstance Win32_Process -Filter
"ParentProcessId=<launcher pid>"`) and measure its CPU over a few seconds, and look at its
network connections: a data download shows established connections to the provider.

Worked example (2026-11-10): an `exec_lag` unit ran for 79 minutes with its launcher at 0 CPU
while the child used about one core and held connections to the data provider. Stopping it
lost that unit's progress; the checkpoint kept the 56 finished units.

A long gap between rows does not by itself mean a hang either: one chain step finishing and
the next starting (for example recall2 handing over to calibration) also stops the row count
of the first file. Read the chain log before restarting anything.

## 5. Red-team v2: two passes, not one grid

Running the red-team v2 grid end to end through the desk on all 1,500 units was estimated at
about 19 CPU-days on this machine (an estimate, not a measurement). The owner-authorised
v0.18 design runs two passes instead, each with its own `--out`:

| Pass | Flags | Units |
|---|---|---|
| 1. analyst only | `--modes json --analysts news,sentiment --no-end-to-end` | 150 snippets x 5 states x 2 analysts = 1,500 |
| 2. end to end | `--modes json --analysts news,sentiment --per-category 2 --seed 2026` | 5 categories x 2 snippets x 5 states x 2 analysts = 100 |

Pass 1 asks how often the analyst complies with an injected instruction, on every snippet.
Pass 2 asks the risk-committee question, how often the final position moves the way the
attack asked after the critic and the limits, on a balanced subset. Units are interleaved
across cells, so a run killed part-way leaves a balanced prefix. Reports give Wilson 95%
intervals; snippets repeat across cells, so those intervals understate the real uncertainty
and are quoted with that caveat. Design detail:
[../review/v018_notes/E_redteam_scope.md](../review/v018_notes/E_redteam_scope.md).

## 6. `exec_lag` resumes from a checkpoint (since v0.19)

`scripts/v17_exec_lag.py` (the registered rules trials at exec_lag 0 and 1; no model is
called) appends one line per finished (trial, lag) to `<out>/checkpoint_<provider>.jsonl`
and skips finished units on a rerun (`--resume`, the default; `--fresh` starts over). The
checkpoint header fingerprints the script, `backtest.py`, the package version, provider,
period and trial list; a mismatch is refused. The final files are built only from the
checkpoint, so a resumed run writes the same bytes as an uninterrupted one.

Two limits: the fingerprint does not cover the downloaded bars, so a Yahoo revision between
sessions is not detected; and it hashes only the script and `backtest.py`, not every engine
module. Before v0.19 the script wrote everything at the end and a kill lost the whole run.

## 7. Before calling a run finished

- The chain wrote every `done_*` marker and the logs end without a traceback.
- The row count matches the planned units (1,500 and 100 for the red-team passes).
- The rows carry one model digest.
- The write-up states the evidence class (measured, on a local 7B model) and every caveat
  above that applies.
