# Chat performance baseline

Captured 2026-09-01, local dev, from a Langfuse trace of a simple query (e.g. "hi" / "when was my last run").

| Metric | Value |
|---|---|
| Input tokens | 17,860 |
| Output tokens | 128 |
| Total tokens | 17,988 |
| `cache_creation_input_tokens` | 0 |
| `cache_read_input_tokens` | 0 |
| Latency | ~4.02s |

## Notes

- `cache_creation_input_tokens` and `cache_read_input_tokens` were both 0 — prompt caching (`cache_control` set on the system prompt and last tool schema in `backend/services/chat_service.py`) did not engage on this call, despite CLAUDE.md listing "Prompt caching — done." Needs investigation: possibly Haiku's higher minimum cacheable-prompt threshold, tool schema ordering instability, or a bug in how the streaming call reports/sends cache fields.
- Input token count is large for a one-line question because every turn resends: full system prompt + memories + conversation summary, all MCP tool schemas (Health + Calendar + local tools), and the full message history for the conversation.

## Purpose

Use this as the "before" number when comparing the impact of future performance work (e.g. fixing prompt caching, trimming tool schemas, reducing history sent per turn). Re-capture a fresh baseline if the benchmark query itself changes.
