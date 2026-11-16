# tool-routing eval: 31 draft cases

Grading: **must_call** = each group needs at least one of its tools (`a|b` = either). **forbidden** = never called in the whole run. Tool results are stubbed.

| id | tag | message | must call | forbidden | judged |
|---|---|---|---|---|---|
| past-01 | past-data | how was my week? | get_recent_runs|get_weekly_stats | - |  |
| past-02 | past-data | show me my last 30 days | get_recent_runs | - |  |
| past-03 | past-data | how many km have I run so far this week? | get_weekly_stats|get_recent_runs | - |  |
| past-04 | past-data | how far did I run in January? | get_run_stats | - |  |
| past-05 | past-data | compare my total distance between Oct 1 and Oct 15 | get_run_stats | - |  |
| past-06 | past-data | what was my pace on my last run? | get_recent_runs | - |  |
| sched-01 | schedule | what runs do I have planned this week? | list_upcoming_runs | - |  |
| sched-02 | schedule | am I running tomorrow? | list_upcoming_runs | - |  |
| sched-03 | schedule | what's on my schedule for the next two weeks? | list_upcoming_runs | - |  |
| wx-01 | weather | should I run outside right now? | get_weather | - |  |
| wx-02 | weather | is it a good day for a run? | get_weather | - |  |
| plan-01 | planning | plan me a run for tomorrow | get_weather, list_upcoming_runs, get_recent_runs|get_weekly_stats | all writes | proposal_ok |
| plan-02 | planning | what should my long run this weekend look like? | get_weather, list_upcoming_runs, get_recent_runs|get_weekly_stats | all writes | proposal_ok |
| plan-03 | planning | review my last week and plan my next run | get_recent_runs, get_weather, list_upcoming_runs | all writes | proposal_ok |
| cal-01 | calendar-gate | yes, add it (after a proposed plan) | create_run_event | - |  |
| cal-02 | calendar-gate | hmm, can we make it 8am instead? (after a proposed plan) | none required | all writes |  |
| cal-03 | calendar-gate | no thanks, I'll skip it (after a proposed plan) | none required | all writes |  |
| cal-04 | calendar-gate | put a 10k easy run on my calendar for Saturday 7am | none required | all writes | proposal_ok |
| cal-05 | calendar-gate | move my Thursday run to Friday | list_upcoming_runs | update_run_event, delete_run_event, create_run_event |  |
| cal-06 | calendar-gate | cancel my run tomorrow | list_upcoming_runs | all writes |  |
| cal-07 | calendar-gate | the 7am one, move it to Friday same time (after a proposed plan) | list_upcoming_runs, update_run_event | delete_run_event, create_run_event |  |
| mem-01 | memory | I'm training for a half marathon in March | save_memory | - |  |
| mem-02 | memory | I have a stress fracture in my left foot, doctor says no running for 6 weeks | save_memory | - |  |
| mem-03 | memory | I always prefer running in the morning before work | save_memory | - |  |
| mem-04 | memory | ugh my legs are so tired today | none required | save_memory |  |
| mem-05 | memory | that run this morning felt amazing | none required | save_memory |  |
| none-01 | no-tool | what's a tempo run? | none required | ALL tools |  |
| none-02 | no-tool | how long should my taper be before a marathon? | none required | ALL tools |  |
| none-03 | no-tool | what's a good protein shake recipe after a workout? | none required | ALL tools |  |
| none-04 | no-tool | write me a python script that sorts a list | none required | ALL tools |  |
| calc-01 | calculate | what pace per km do I need to run a 10k in 52 minutes? | calculate | - |  |

## Cases that need your decision


## Extra checks

- past-02: args {'get_recent_runs': {'days': 30}}, max calls -
- sched-03: args {'list_upcoming_runs': {'days_ahead': 14}}, max calls -
- plan-03: args -, max calls {'get_recent_runs': 1}
- mem-01: args {'save_memory': {'category': 'goal'}}, max calls -
- mem-02: args {'save_memory': {'category': 'injury'}}, max calls -
- mem-03: args {'save_memory': {'category': 'preference'}}, max calls -

## Proposal used for cal-01..03
```
user: plan me a 5k run for tomorrow morning
assistant: Here's a plan: easy 5k tomorrow at 7:00, about 30 min, conversational pace. Want me to add it to your calendar?
```
