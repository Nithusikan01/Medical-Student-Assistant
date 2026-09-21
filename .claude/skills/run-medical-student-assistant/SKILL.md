---
name: run-medical-student-assistant
description: Build, launch and drive the Medical-Student-Assistant RAG app locally - start the backend API, the Vite frontend and a throwaway Postgres, then run a real authenticated query and inspect the telemetry trace it produced. Use when asked to run, start, serve, smoke-test, screenshot or debug the app, verify a change works in the real app, or check that tracing and spans are being written.
---

# Running Medical-Student-Assistant

FastAPI backend (`backend/`) + React/Vite frontend (`frontend/`) + a `rag`
engine library, backed by Postgres, Pinecone and Gemini.

Paths below are relative to the repository root. Verified on **Windows 11**
with Git Bash and PowerShell — this is not a Linux container, and the two
shells are not interchangeable here (see Gotchas).

**The agent path is `driver.py`.** The API is behind JWT auth and the whole
point of the app — the RAG pipeline and the telemetry it emits — only happens
on an authenticated `POST /api/query`. Curling `/health` proves nothing.

## The one thing to get right first

`backend/.env` has a **`DATABASE_URL` pointing at a hosted database.** Never
let a local run migrate or write to it. Every command below overrides
`DATABASE_URL` in the shell environment, which works because `app.py` calls
`load_dotenv()` without `override=True` — a shell variable wins over `.env`.

If you skip the override, `alembic upgrade head` will alter a live database.

## Prerequisites

Already installed in this environment; not re-verified this session:

```bash
python -m pip install -e "./rag[dev]"
python -m pip install -e "./backend[dev]"
```

Confirm instead of reinstalling:

```bash
python -m pip show rag-engine rag-backend | grep -E "^(Name|Editable)"
```

Lint and format tooling **must** match the CI pins, or you will reformat
dozens of untouched files:

```bash
python -m pip install "black==25.1.0" "ruff==0.16.6"
```

## 1. Start Postgres

Docker Desktop's daemon is usually not running. Start it and wait (PowerShell):

```powershell
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
foreach ($i in 1..40) { Start-Sleep -Seconds 5; $v = (docker info --format '{{.ServerVersion}}' 2>$null); if ($LASTEXITCODE -eq 0 -and $v) { "daemon up, server $v"; break } }
```

Then a throwaway container on **5433** (not 5432, to avoid colliding with any
local install):

```bash
docker rm -f msa-local-pg >/dev/null 2>&1
docker run -d --name msa-local-pg \
  -e POSTGRES_PASSWORD=localdev -e POSTGRES_DB=medical_assistant \
  -p 5433:5432 postgres:16
```

Wait with a **real query**, not `pg_isready` (see Gotchas):

```bash
for i in $(seq 1 60); do
  docker exec msa-local-pg psql -U postgres -d medical_assistant -c "select 1;" >/dev/null 2>&1 && break
done
```

## 2. Migrate

From `backend/` — Alembic resolves `alembic.ini` and `migrations/` relative
to it:

```bash
cd backend
export DATABASE_URL="postgresql+psycopg://postgres:localdev@127.0.0.1:5433/medical_assistant"
python -m alembic upgrade head
```

Expect six revisions, `0001` → `0006`.

## 3. Start the API

```bash
cd backend
export DATABASE_URL="postgresql+psycopg://postgres:localdev@127.0.0.1:5433/medical_assistant"
export APP_ENV=local APP_VERSION=local-dev
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Startup is healthy when the log shows, in order:

```
Database schema is up to date (0006).
Index client created for host https://...pinecone.io
History-aware RAG system initialized successfully.
Telemetry writer started.
```

`Telemetry writer started.` is the line that matters for observability work.
Its absence means `TELEMETRY_ENABLED=false` or the sink failed to build.

On a **freshly migrated** database there is one extra line,
`Seeded administrator account '...'`. Admin seeding is idempotent, so it does
not reappear on later starts - its absence on a restart is correct.

## 4. Drive it (agent path)

```bash
python .claude/skills/run-medical-student-assistant/driver.py smoke "Which hormones does the thyroid gland produce?"
```

Health-checks, logs in as the seeded admin from `backend/.env`, runs a real
query, waits for the telemetry flush, then prints the span tree and the
operational metrics. Real output from this session:

```
query: 200  trace=d7311537eeea4c03a581b43c818a0485
  model               gemini-flash
  processing_time_ms  8838
  sources             5

  stage                    ms  status  parent
  memory_load             9.7  ok      (root)
  query_rewrite        2932.3  ok      (root)
  retrieval            4138.1  ok      (root)
  dense_retrieval      3051.8  ok      retrieval
  query_embedding      1067.1  ok      dense_retrieval
  bm25_retrieval          0.9  ok      retrieval
  fusion                  0.5  ok      retrieval
  reranking            1083.5  ok      retrieval
  context_build           0.4  ok      (root)
  generation           1691.9  ok      (root)
```

Other commands:

```bash
python .claude/skills/run-medical-student-assistant/driver.py health
python .claude/skills/run-medical-student-assistant/driver.py login
python .claude/skills/run-medical-student-assistant/driver.py query "What is the function of insulin?"
python .claude/skills/run-medical-student-assistant/driver.py trace            # most recent
python .claude/skills/run-medical-student-assistant/driver.py trace <trace_id>
python .claude/skills/run-medical-student-assistant/driver.py metrics --hours 6
```

Raw SQL when you need something the driver does not print:

```bash
docker exec msa-local-pg psql -U postgres -d medical_assistant -c \
  "select route, status_code, count(*) from rag_traces group by 1,2 order by 3 desc;"
```

## 5. Frontend (optional)

Only needed to look at the UI. **Use PowerShell** — `npm` is broken under Git
Bash here:

```powershell
Set-Location "frontend"
Start-Process -FilePath "npm.cmd" -ArgumentList "run","dev" -RedirectStandardOutput "$env:TEMP\vite.log" -RedirectStandardError "$env:TEMP\vite.err" -WindowStyle Hidden
```

Open **`http://localhost:5173`** — *not* `127.0.0.1:5173`, which refuses the
connection. Vite proxies `/api` and `/health` to port 8000, and the
`X-Trace-ID` / `X-Request-ID` headers survive the proxy.

## 6. Tests

```bash
cd rag     && python -m pytest tests/unit -q     # 108 passed
cd backend && python -m pytest tests/unit tests/api -q   # 304 passed, ~65s
python -m black --check rag/src rag/tests backend/src backend/tests
python -m ruff check rag/src rag/tests backend/src backend/tests
```

Tests need no Postgres, no Docker and no credentials — they use a throwaway
SQLite file per test.

## Teardown

```bash
docker rm -f msa-local-pg
```

Stop the uvicorn and Vite processes separately.

## Gotchas

- **`backend/.env` points `DATABASE_URL` at a hosted database.** Always
  override it in the shell. Hosted AWS RDS is *not* reachable from a laptop —
  the deploy workflow runs migrations as an ECS task inside the VPC precisely
  because of that — so don't burn time trying.
- **`pg_isready` lies on a fresh container.** It reports ready against the
  temporary bootstrap server postgres runs during `initdb`, and the very next
  command fails with `the database system is shutting down`. Poll with
  `psql -c "select 1;"` instead.
- **`npm` does not work under Git Bash here.** MSYS path translation mangles
  its prefix into
  `C:\ProgramData\anaconda3\Library\c\Users\...\npm-cli.js` and it dies with
  `MODULE_NOT_FOUND`. `node` is fine; only `npm` breaks. Use PowerShell.
- **Vite binds IPv6 only.** `http://127.0.0.1:5173` refuses the connection;
  `http://localhost:5173` works. Curl smoke tests must use `localhost`.
- **Telemetry is not written synchronously.** A background thread flushes on
  an interval, so a trace is absent for up to ~1s after its response returns.
  The driver polls for it; hand-written checks must too.
- **`/health/health` is deliberately excluded from tracing**, so it produces
  no rows. Absence there is correct, not a bug.
- **BM25 returns nothing on a fresh local database.** The lexical index is
  built from `document_chunks`, which is empty until a PDF is ingested
  locally, so hybrid retrieval silently degrades to dense-only
  (`bm25_count: 0`, `overlap_count: 0` in the fusion span). Pinecone still
  returns real chunks, so queries answer correctly. Not a bug — ingest a PDF
  through the admin UI if you need the lexical half.
- **Span `started_at` ties, so span order is not reliable.** The wall clock
  here is coarser than the gap between a parent span and the child it opens:
  `retrieval`, `dense_retrieval` and `query_embedding` routinely share one
  timestamp to the microsecond. `duration_ms` is unaffected - it comes from
  `perf_counter` - but any `ORDER BY started_at` renders a scrambled
  waterfall. The driver breaks ties on `ended_at DESC`, which keeps parents
  above children; siblings starting in the same tick can still appear out of
  order. A monotonic per-trace sequence column is the real fix.
- **First query is slow** (~8–11s): a Gemini call for query rewriting, a
  hosted embedding call, a hosted rerank, then generation.
- **Run uvicorn and alembic from `backend/`.** `.env`, `storage/` and
  `alembic.ini` all resolve relative to it.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `failed to connect to the docker API at npipe:...dockerDesktopLinuxEngine` | Docker Desktop is not running. Start it (step 1) and wait for the daemon. |
| `psql: FATAL: the database system is shutting down` | The container is still running `initdb`. Poll with `select 1;` until it answers. |
| `ValueError: DATABASE_URL environment variable is not set` | You are not in `backend/` or did not export the override. |
| `Cannot reach http://127.0.0.1:8000/...: [WinError 10061]` | API not running, or started on another port. |
| `Error: Cannot find module '...\npm-cli.js'` | You ran `npm` from Git Bash. Use PowerShell. |
| `curl: (7) Failed to connect to 127.0.0.1 port 5173` | Use `localhost:5173`; Vite bound IPv6 only. |
| `trace ... has not been flushed after 6s` | Telemetry disabled (`TELEMETRY_ENABLED`), or the writer cannot reach the database — check the API log for `Failed to write ... telemetry records`. |
| `black` reformats ~27 untouched files | Wrong version. Install `black==25.1.0` and `ruff==0.16.6` to match CI. |
