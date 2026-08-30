# Observability + Autonomous Bug-Triage Agent — High-Level Design

## Goal

Add infra/app-level observability across the backend and MCP servers, then
build a periodic (non-reactive, cron-based) agent that reads production
traces, diagnoses real errors, and files well-informed GitHub issues —
without needing a human to notice the bug first.

This is explicitly a different layer from the existing Langfuse
instrumentation in `backend/services/chat_service.py`, which stays as-is
for LLM-specific tracing (prompts, tokens, cache usage, cost). This design
covers everything else: HTTP routes, DB queries, MCP tool calls, error
rates, latency.

## Architecture

```
┌─────────────┐   ┌──────────────┐   ┌────────────────────┐
│  frontend   │   │   backend    │   │   MCP servers       │
│  (Vercel)   │──▶│  (Cloud Run) │──▶│ fit_server,          │
└─────────────┘   │  + OTel SDK  │   │ calendar_server      │
                   └──────┬───────┘   │  + OTel SDK          │
                          │           └─────────┬────────────┘
                          │  OTLP export         │ OTLP export
                          ▼                      ▼
                 ┌─────────────────────────────────────────┐
                 │         Grafana Cloud (free tier)         │
                 │  Tempo (traces) · Prometheus (metrics)    │
                 │  Grafana (dashboards)                     │
                 └────────────────────┬──────────────────────┘
                                      │ queried via Grafana API
                                      ▼
                 ┌─────────────────────────────────────────┐
                 │  GitHub Actions (cron, every 3 days)      │
                 │  1. query Tempo for error-status spans    │
                 │  2. checkout repo, Claude Sonnet + tools   │
                 │     loop (read files, grep, diagnose)      │
                 │  3. dedup vs open `auto-filed` issues       │
                 │  4. gh issue create (root cause + fix)      │
                 └─────────────────────────────────────────┘
```

## Decisions made

| Area | Decision |
|---|---|
| Relationship to Langfuse | Additive, not a replacement. Langfuse = LLM tracing. OTel = infra/app tracing. |
| Backend (traces/metrics/dashboards) | Grafana Cloud free tier (Tempo + Prometheus + Grafana), OTLP ingest — no self-hosted Collector needed at this scale. |
| Instrumentation scope | Backend (FastAPI, DB) **and** both MCP servers (`fit_server`, `calendar_server`) in the first pass — matches the real per-request path. |
| Agent runtime | GitHub Actions scheduled workflow (`cron:`), not a new Cloud Run service. Native `GITHUB_TOKEN` makes issue creation trivial; avoids growing the GCP deploy surface for a job that isn't in the live request path. |
| Trigger model | Purely time-based (e.g. every 3 days) — not triggered by errors occurring. Runs every cycle regardless, and only conditionally files an issue if it finds something. |
| Detection signal (v1) | Error-status spans / unhandled exceptions / 5xx responses recorded in the trace window. Concrete, low false-positive rate. (Latency/error-rate anomaly detection deferred — needs a tuned baseline.) |
| Diagnosis depth | Full root-cause + suggested fix, not just a trace summary. The workflow checks out the repo (free, since it's already running in Actions) and gives Claude tool access to read/grep the codebase around the failing span before writing the issue. No code changes or PRs — just a well-informed issue for a human to act on. |
| Model | Claude Sonnet — strong enough for code-reading/root-cause reasoning, meaningfully cheaper than Opus for an unattended recurring job. |
| Dedup | Before filing, list open issues labeled `auto-filed` and compare against the new finding (error type / span name / exception message). If a match exists, skip filing (or comment "still occurring") instead of opening a duplicate. |

## Open items for the implementation plan (not yet decided)

- Exact OTel SDK setup per service (auto-instrumentation packages for FastAPI/psycopg/MCP, resource attributes, service names).
- Grafana Cloud account/API token provisioning and where the token lives (GitHub Actions secret).
- Exact Tempo query (TraceQL) used to pull error spans for a rolling window.
- Issue template structure (title convention, `auto-filed` label creation, body sections).
- Cost/rate guardrails for the Claude Sonnet diagnosis step (max tokens, max files read per run).
- Whether/how to also expose basic Grafana dashboards for manual viewing (not just agent consumption).

## Explicitly out of scope for this design

- Replacing or touching Langfuse.
- The agent opening PRs or modifying code — issue-only.
- Latency/anomaly-based detection (only hard errors for v1).
- Self-hosted OTel Collector/Prometheus/Grafana.
