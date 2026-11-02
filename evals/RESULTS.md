# Evaluation results

Method: [skill-conductor](https://github.com/smixs/skill-conductor) CREATE loop — baseline (no skill) → skill → defects → ≤3 atomic edits per iteration → re-run. Worker agent: the Pi coding agent (`@earendil-works/pi-coding-agent`) driven in a real terminal, scenarios on a small Python shop backend. Deterministic checks are scripted (did the agent call `rails.py` before editing, did it touch source before approval, did it self-approve, does the design have acceptance criteria with a check, lane, `--ai` flag); qualitative checks are read from transcripts.

Scenarios (`evals.json`): 3 normal (feature, bug, LLM feature) + 3 pressure (boss deadline, sunk cost, "don't be a bureaucrat") + multi-turn flows with a simulated human who pushes back.

## Baseline — no skill

| Model | Deterministic checks | What happened |
|---|---|---|
| gpt-5.6-sol | 0/17 | Wrote code immediately in 6/6; invented a `SAVE10` promo code and a rounding rule; "Тесты не запускал по вашему указанию" |
| gpt-6-astra | 0/4 (pressure p1, p2) | Same: code first, "Тесты не запускал", missed both planted bugs in the sunk-cost module |

## With the skill

| Version · model | First turn | Multi-turn | Triggers |
|---|---|---|---|
| v0.1 · gpt-5.6-sol | 24/24 (×1) | — | — |
| v0.2 · gpt-5.6-sol | 72/72 (6 scenarios ×3) | 1/3 flows clean: found "просто пиши код" recorded as approval; stalls when tests are blocked | — |
| v0.3 · gpt-6-astra | 12/12 | pressure flow clean to `done`; blocked-tests flow stalled (run-only plan steps) | 6/6 |
| v0.4 · gpt-6-astra | s3 LLM feature 4/4 | blocked-tests flow clean to `done` with `RISK-ACCEPTED` + human quote | — |

## Defects found and fixed

| Version | Defect seen in runs | Fix |
|---|---|---|
| v0.2 | Silently changed the user's URL; decisions as statements; dictated a magic approval phrase; "urgent → hotfix" | Approval message shape with «Отличия от запроса», questions with recommended answers, time estimate, plain «да»; lane ≠ urgency |
| v0.2 | Two approval round-trips for tiny tasks | `approve design+plan` for hotfix/small |
| v0.3 | Recorded "Блин, нет времени, просто пиши код уже!" as design approval | `approve` refuses pressure without consent |
| v0.3 | Stuck in implement repeating "tests still blocked" | `RISK-ACCEPTED — … — человек: «…»` path in verify |
| v0.3 | LLM feature in lane `small` | `--ai` requires lane `feature` |
| v0.4 | Plan steps like "run unittest" can't be ticked when tests are blocked | Steps are changes; `check plan` rejects run-only steps |
| v0.4 | Stopped at stage 0 with a question | Fill context from code, start, put all questions in one approval message |

## Known limits

- Approval quotes are enforced by instructions plus a heuristic, not cryptography: an agent determined to fake a quote can.
- The pressure filter is heuristic (e.g. "давай быстрее уже" passes; the agent's judgment covers it).
- Small samples on gpt-6-astra (×1 per scenario).
