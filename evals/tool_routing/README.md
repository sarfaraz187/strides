# Tool-routing eval: how it runs

An eval is a list of test cases, a runner that calls the coach on each one, and a grader that says pass or fail. Here it is plain Python in `run_eval.py`. Nothing runs by itself: it starts only when you type the command.

## Run it

```
uv run python evals/tool_routing/run_eval.py --selftest            # free, checks the grader
uv run python evals/tool_routing/run_eval.py --judge-check         # tiny paid check of the judge
uv run python evals/tool_routing/run_eval.py --approve-harness --variant baseline
uv run python evals/tool_routing/run_eval.py --variant baseline     # later runs, no approval flag (add --reps 3 for a steadier score)
```

`--approve-harness` records a hash of the runner, `cases.jsonl` and `uv.lock`. If any of them change, the runner refuses to run until you approve again. Only you pass this flag.

## What happens, in order

```
uv run python evals/tool_routing/run_eval.py --variant baseline

1. main()                       reads your flags (reps, variant, model)
2. enforce_harness_gate()       checks the approval hash. Stops here if the code changed.
3. install_edge_stubs()         fakes the DB, Langfuse and JWT
4. load_mcp_tool_schemas()      reads the 8 MCP tool definitions from your server code
5. build_app()                  loads the real prompt, wires fake tools into the real coach
6. load_cases()                 reads the cases from cases.jsonl
7. skip finished work           looks at results.jsonl, drops (case, rep) pairs already done
8. start the runs               every (case, rep) job, 4 at a time
```

## One job, for "how was my week?"

```
messages = [user: "how was my week?"]
        |
real process_query --> Haiku 4.5 --> "call get_weekly_stats"   (API call 1)
        |                                 |
        |                       stub returns {"total_distance_km": 23.3, ...}
        |
        +--> Haiku 4.5 --> "You ran 23.3 km this week..."       (API call 2)
        |
record: tools_called = ["get_weekly_stats"], tokens, latency
        |
grade_case(): routing_ok? safety_ok? args_ok? --> pass
        |
(judge runs here only for cases marked judge: proposal)
        |
write one line to results.jsonl and a transcript to traces/
```

After all jobs finish, `print_summary()` prints pass rates with confidence ranges.

## What is real and what is fake

Real: the system prompt, the model, the 10 tool schemas, the `process_query` tool loop.
Fake: tool results (canned), the database, Langfuse.

## The grader

```
routing_ok     every must_call group has a tool that was called   (a|b means either)
safety_ok      no forbidden tool was called
args_ok        e.g. days == 30 on get_recent_runs
efficiency_ok  no tool called more than max_calls
proposal_ok    Haiku 5.5 judge reads the reply, 4 cases only (plan-01..03, cal-04)
pass           every check that applies is true
```

The judge is a grader inside this one eval, not a separate eval. It checks the reply names a specific run, asks to confirm, and does not hand the decision back as open questions.

## Files

```
cases.md / cases.jsonl     this folder   the test cases (md to read, jsonl to run)
baseline/results.jsonl    one row per (case, rep): grade, tools called, tokens, reply
<variant>/traces/          full transcript per run
<variant>/errors.jsonl     failed attempts, never counted as scores
_state.json                metric names and model prices for the report
```

## Cost

About half a cent per run on Haiku 4.5 (around 5,300 input tokens, two model calls when a tool is used). Default is 1 rep: 31 runs, about $0.17. 3 reps is about $0.50 and cuts the noise from about 18 to 10 points.

## Decisions baked into the cases

- Coach must propose a plan and get a yes before any calendar write, even when the user names the plan.
- Move or cancel: list the events, ask which run if several match, then write only after the user picks.
- Planning questions: gather weather, upcoming runs and recent runs first, then propose.
- Pace math uses the `calculate` tool.
