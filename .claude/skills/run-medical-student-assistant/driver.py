#!/usr/bin/env python
"""
Drive the running Medical-Student-Assistant stack.

This is the agent-facing handle on the app. The API is behind JWT auth and
the interesting behaviour (the RAG pipeline, and the telemetry it emits) only
happens on an authenticated POST, so "run it and curl /health" proves almost
nothing. This logs in with the seeded admin, asks a real question, and then
reads back the trace the request produced.

Dependency-free apart from psycopg, which the backend already depends on.
Uses urllib rather than httpx so it runs even outside the backend's venv.

    python .claude/skills/run-medical-student-assistant/driver.py smoke

Commands:

    health              GET /health/health
    login               authenticate as the seeded admin, print a masked token
    query "<question>"  full RAG request; prints trace id, timing and sources
    trace [<id>]        span tree for a trace (default: most recent)
    metrics             operational metrics over the last hour
    smoke               health + login + query + trace + metrics  (default)

Nothing here writes to the application other than by using it as a user
would: it creates one conversation and one set of telemetry rows per query.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / "backend" / ".env"

DEFAULT_BASE = "http://127.0.0.1:8000"

# The throwaway container the skill tells you to start. Deliberately not the
# DATABASE_URL from backend/.env: that points at a hosted database, and this
# driver must never be the thing that touches it by accident.
DEFAULT_DB = "postgresql://postgres:localdev@127.0.0.1:5433/medical_assistant"


# ----------------------------------------------------------------------
# Environment
# ----------------------------------------------------------------------


def read_env() -> dict[str, str]:
    """Parse backend/.env without importing dotenv."""

    if not ENV_FILE.exists():
        sys.exit(f"No {ENV_FILE}. Copy backend/.env.example and fill it in.")

    values: dict[str, str] = {}

    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()

    return values


# ----------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------


def call(base, path, payload=None, token=None, method=None, timeout=180):
    data = json.dumps(payload).encode() if payload is not None else None

    request = urllib.request.Request(
        base + path,
        data=data,
        method=method or ("POST" if data else "GET"),
    )

    if data:
        request.add_header("Content-Type", "application/json")

    if token:
        request.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            return response.status, dict(response.headers), json.loads(body or b"{}")
    except urllib.error.HTTPError as error:
        body = error.read()
        return error.code, dict(error.headers), json.loads(body or b"{}")
    except urllib.error.URLError as error:
        sys.exit(f"Cannot reach {base}{path}: {error.reason}\nIs the API running?")


def cmd_health(args) -> None:
    status, _, body = call(args.base, "/health/health")

    print(f"health: {status} {body}")

    if status != 200:
        sys.exit(1)


def login(args) -> str:
    env = read_env()

    status, headers, body = call(
        args.base,
        "/api/auth/login",
        {"email": env["ADMIN_EMAIL"], "password": env["ADMIN_PASSWORD"]},
    )

    if status != 200:
        sys.exit(f"login failed: {status} {body}")

    token = body["access_token"]

    print(f"login: {status}  user={body['user']['email']}  role={body['user']['role']}")
    print(f"       trace={headers.get('x-trace-id', '-')}  token={token[:12]}...")

    return token


def cmd_login(args) -> None:
    login(args)


def cmd_query(args) -> None:
    token = login(args)

    conversation_id = str(uuid.uuid4())

    status, headers, body = call(
        args.base,
        "/api/query",
        {"conversation_id": conversation_id, "question": args.question},
        token=token,
    )

    if status != 200:
        sys.exit(f"query failed: {status} {body}")

    trace_id = headers.get("x-trace-id", "-")

    print(f"\nquery: {status}  trace={trace_id}")
    print(f"  model               {body.get('model')}")
    print(f"  processing_time_ms  {body.get('processing_time_ms')}")
    print(f"  sources             {len(body.get('sources', []))}")

    for source in body.get("sources", [])[:3]:
        metadata = source.get("metadata", {})
        print(
            f"    - {metadata.get('filename')} "
            f"chunk={metadata.get('chunk_index')} "
            f"score={source.get('score'):.4f}"
        )

    print(f"\n  answer: {(body.get('answer') or '')[:300]}")

    if trace_id != "-":
        print()

        if wait_for_trace(args, trace_id):
            show_trace(args, trace_id)
        else:
            print(
                f"trace {trace_id} has not been flushed after "
                f"{TRACE_WAIT_SECONDS:.0f}s - telemetry disabled, or the "
                f"writer cannot reach the database (check the API log)."
            )


# ----------------------------------------------------------------------
# Telemetry
# ----------------------------------------------------------------------


def connect(args):
    try:
        import psycopg
    except ImportError:
        sys.exit("psycopg is not installed; run this from the backend's environment.")

    # SQLAlchemy's driver suffix is not valid libpq.
    url = args.db.replace("postgresql+psycopg://", "postgresql://")

    try:
        return psycopg.connect(url, connect_timeout=10)
    except Exception as error:  # noqa: BLE001 - the message is the whole point
        sys.exit(f"Cannot reach the database at {url.split('@')[-1]}: {error}")


# Telemetry is written by a background thread on a flush interval, so a
# trace is not in the database the instant its response returns. Asking
# immediately - which is exactly what `query` does - reliably misses it.
TRACE_WAIT_SECONDS = 6.0


def wait_for_trace(args, trace_id: str) -> bool:
    deadline = time.monotonic() + TRACE_WAIT_SECONDS

    while time.monotonic() < deadline:
        with connect(args) as connection, connection.cursor() as cursor:
            cursor.execute("select 1 from rag_traces where id = %s", (trace_id,))

            if cursor.fetchone() is not None:
                return True

        time.sleep(0.5)

    return False


def show_trace(args, trace_id: str | None = None) -> None:
    with connect(args) as connection, connection.cursor() as cursor:
        if trace_id is None:
            cursor.execute("select id from rag_traces order by started_at desc limit 1")
            row = cursor.fetchone()

            if row is None:
                print("no traces recorded yet")
                return

            trace_id = row[0]

        cursor.execute(
            """
            select route, status, status_code, duration_ms, environment, app_version
            from rag_traces where id = %s
            """,
            (trace_id,),
        )
        trace = cursor.fetchone()

        if trace is None:
            print(f"no trace {trace_id}")
            return

        route, status, status_code, duration_ms, environment, app_version = trace

        print(f"trace {trace_id}")
        print(
            f"  {route}  {status} {status_code}  "
            f"{duration_ms:.0f}ms  [{environment} {app_version}]"
        )

        cursor.execute(
            """
            select s.stage, s.duration_ms, s.status, p.stage, s.meta
            from rag_spans s
            left join rag_spans p on p.id = s.parent_span_id
            where s.trace_id = %s
            -- started_at alone ties: the wall clock is coarser than the gap
            -- between a parent span and the child it opens. Breaking ties on
            -- ended_at descending at least puts parents above their children.
            -- Siblings that start within the same clock tick can still show
            -- out of order; see the skill's Gotchas.
            order by s.started_at, s.ended_at desc
            """,
            (trace_id,),
        )

        rows = cursor.fetchall()

        if not rows:
            print("  (no spans - is this a non-query route?)")
            return

        print(f"\n  {'stage':<18}{'ms':>9}  status  parent")

        for stage, span_ms, span_status, parent, _meta in rows:
            print(
                f"  {stage:<18}{span_ms:>9.1f}  {span_status:<7} "
                f"{parent or '(root)'}"
            )

        # The two numbers most worth eyeballing after a change.
        for stage, _ms, _status, _parent, meta in rows:
            if meta and "total_tokens" in meta:
                print(f"\n  tokens[{stage}] = {meta['total_tokens']}")


def cmd_trace(args) -> None:
    show_trace(args, args.trace_id)


def cmd_metrics(args) -> None:
    """The Phase 5 aggregation layer, over whatever is in the database."""

    sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))
    sys.path.insert(0, str(REPO_ROOT / "rag" / "src"))

    from datetime import UTC, datetime, timedelta

    import psycopg
    from backend.observability.aggregation import (
        SpanPoint,
        TimeWindow,
        TracePoint,
        summarize_requests,
        summarize_stages,
    )

    window = TimeWindow(
        start=datetime.now(UTC) - timedelta(hours=args.hours),
        end=datetime.now(UTC),
    )

    url = args.db.replace("postgresql+psycopg://", "postgresql://")

    with (
        psycopg.connect(url, connect_timeout=10) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
            select started_at, duration_ms, status, status_code, route
            from rag_traces where started_at >= %s and started_at < %s
            """,
            (window.start, window.end),
        )
        traces = [TracePoint(*row) for row in cursor.fetchall()]

        cursor.execute(
            """
            select stage, duration_ms, status
            from rag_spans where started_at >= %s and started_at < %s
            """,
            (window.start, window.end),
        )
        spans = [SpanPoint(*row) for row in cursor.fetchall()]

    summary = summarize_requests(traces, window)

    print(f"last {args.hours}h: {summary.total} requests")
    print(
        f"  ok={summary.succeeded} client_errors={summary.client_errors} "
        f"failed={summary.failed} success={summary.success_rate:.0%}"
    )

    if summary.latency.percentiles:
        points = {
            name: round(value)
            for name, value in summary.latency.percentiles.items()
            if name in ("p50", "p95", "p99")
        }
        print(f"  latency ms {points}")

    print("\n  slowest stages (p95 ms):")

    for stage in summarize_stages(spans)[:8]:
        print(
            f"    {stage.stage:<18}{stage.latency.p95:>9.1f}  "
            f"n={stage.count} errors={stage.errors}"
        )


def cmd_smoke(args) -> None:
    cmd_health(args)
    print()
    args.question = args.question or "What are the main topics covered?"
    cmd_query(args)
    print()
    cmd_metrics(args)


# ----------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--hours", type=float, default=1.0)

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("health")
    sub.add_parser("login")

    query = sub.add_parser("query")
    query.add_argument("question")

    trace = sub.add_parser("trace")
    trace.add_argument("trace_id", nargs="?")

    sub.add_parser("metrics")

    smoke = sub.add_parser("smoke")
    smoke.add_argument("question", nargs="?")

    args = parser.parse_args()

    handlers = {
        "health": cmd_health,
        "login": cmd_login,
        "query": cmd_query,
        "trace": cmd_trace,
        "metrics": cmd_metrics,
        "smoke": cmd_smoke,
        None: cmd_smoke,
    }

    if args.command in (None, "smoke") and not hasattr(args, "question"):
        args.question = None

    handlers[args.command](args)


if __name__ == "__main__":
    main()
