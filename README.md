# LoopedBankingAgent

Can a fixed open-weight model improve its own agent by rewriting only the prompt
harness, and can you actually measure whether it did?

Everything here runs on [τ²-bench](https://github.com/sierra-research/tau2-bench)'s
`banking_knowledge` domain: 97 customer-service tasks over a 698-document policy
base, scored on the end state of a database rather than on what the agent says.
One model, Qwen3.8-27B, plays all three roles. It is the agent handling the
customer, the simulated customer, and the "fixer" that reads failure traces and
rewrites the agent's rulebook.

The short version. My pre-registered version of this idea produced no lift at
all. Auditing it turned up two defects in my method rather than in the model.
After fixing those, the model wrote a harness that beat the control by 0.133 on
the development set, and adding step-budget awareness took that to 0.400 against
a 0.200 control. On held-out tasks the same configuration gained 0.100, at one
trial, which sits inside the noise floor I measured. So the method works on the
tasks it was tuned against, and it has not yet been shown to transfer.

Total project cost was about $55 across 248 scored runs and 205M tokens. Every
result in this repo was committed by CI straight from the run that produced it.

## Results

Development set, 10 tasks at 3 trials each, so 30 executions per row. Reward is
the per-task mean over trials, in {0, .33, .67, 1.0}.

| Configuration | Mean | Solved | Never finished | Wrong but finished |
|---|---|---|---|---|
| No harness (control) | 0.200 | 6/30 | 10/30 | 14/30 |
| Model-authored harness | 0.333 | 10/30 | 9/30 | 11/30 |
| **Harness plus step budget** | **0.400** | **12/30** | 7/30 | 11/30 |

Held-out set, 10 pre-registered tasks that had never been run, at 1 trial.

| Configuration | Mean | Solved | Never finished |
|---|---|---|---|
| No harness (control) | 0.100 | 1/10 | 5/10 |
| **Harness plus step budget** | **0.200** | 2/10 | 3/10 |

The two components help for different reasons, which is why they add up on dev.
The harness mostly converted wrong-but-finished runs into solved ones (14 down
to 11) and barely moved non-convergence. The step budget did the reverse, cutting
non-convergence from 10 to 7 while wrong-but-finished stayed flat, so the runs it
freed up came back correct rather than rushed.

The held-out result is weaker and I am not going to dress it up. A one-task gap
at one trial is the same size as the noise floor, so it does not establish a
lift. What is more telling is each arm against its own dev behaviour: the control
scored 1/10 on holdout, which is inside its dev range of 1 to 3, while the
harness configuration scored 2/10 against a dev range of 3 to 5. The control held
steady on unseen tasks and the treatment dropped. That is what partial
overfitting looks like, and it is roughly what I expected given the harness was
written from failures on the dev set.

Three trials on the holdout would settle it. That run has not been done.

## What I actually found

### The scoreboard was noise, and it cost me a result

Running the identical no-harness control three times on the same ten tasks gave
2/10, then 3/10, then 1/10. Standard deviation of one full task, with two of the
ten flipping between runs. Nothing changed except sampling. The provider does not
honour `seed` even at temperature 0.

I had already written down an earlier configuration's 3/10 as "first positive
movement." It was inside the noise band, so I deleted it. The worse consequence
was structural: my keep-or-revert gate had one task of resolution against one
task of noise, so it had been accepting and rejecting changes on coin flips.
Everything after this uses three trials and a margin of 0.10.

### The model was not weak, it was blind

The fixer failed twice before this. Both failures came from how I had built it.

Its evidence contained no tool responses, so error strings like
`cannot be closed. Current status: FROZEN`, which turned out to be the single
biggest waster of steps, were simply invisible to it. It was diagnosing from
behaviour alone. Separately, the prompt I gave it implied that a rule was a
constraint, and nothing else. Both of its attempts were constraints, which in
hindsight is the only move I had shown it.

Once it could see the full call-and-response trace and knew a rule could also be
a procedure or a checklist, the same model found the freeze-before-close ordering
bug itself and wrote a working procedure on its first try.

### Procedures worked, policies cost steps

Five fixer iterations produced exactly one keeper, and the pattern across them is
the most useful thing I learned.

| Iteration | What the model changed | Mean | Outcome |
|---|---|---|---|
| v1-1 | Tightened the search-precision constraint | 0.100 | reverted |
| v1-2 | Added a strict action gate | 0.100 | reverted |
| v2-1 | Wrote seven procedures from an empty file | **0.333** | **kept** |
| v2-2 | Added an escalation gate above them | 0.233 | reverted |
| v2-3 | Added a workflow checklist above them | 0.200 | reverted |

(The first two ran at one trial and are directional only.)

Every attempt that layered a restriction on top of existing rules made things
worse. The one that worked replaced nothing and simply described how to do the
job. The termination data shows the mechanism: both layered restrictions pushed
non-convergence to 13/30 and 12/30, which is worse than having no harness at all.
Deliberation costs turns, and this agent only has about 26 of them.

The clearest case is iteration 2, which added "confirm scope with the customer
before disputing or replacing a card." That is good customer service. It made the
agent wrong slightly less often, 11 down to 10, but non-convergence went from 9
to 13 and solved dropped from 10 to 7. It traded three completed tasks for one
avoided mistake, and the gate reverted it.

## Cost and caching

Recorded per-message cost, 30 executions per row.

| Arm | Recorded | List | Cache discount | Prompt tokens | Runtime |
|---|---|---|---|---|---|
| Harness only | $5.59 | $12.28 | 54% | 24.7M | 180 min |
| Harness plus step budget | $9.57 | $9.91 | 3% | 19.7M | 246 min |

Step-budget awareness rewrites the system message on every turn, which destroys
prompt caching. The result is 20% fewer prompt tokens, 71% more spend and 36%
more wall-clock time. This reproduced exactly on the held-out run, where the
control kept a 50% cache discount and the step-budget arm got 4%.

It is a cheap mistake to make and an invisible one until you look at the bill.
The fix is to append the budget as a trailing message instead of mutating the
cacheable prefix, which I have specced but not tested.

Cost per solved task on the best dev run was $0.80. Worth noting that failures
are the expensive ones: on a representative trial a failed task averaged $0.40
against $0.24 for a solved one, because a lost agent runs to the turn cap while a
competent one finishes in about half that. Seventy-one percent of the spend on
that trial produced no reward.

## Why this is not a leaderboard number

**I do not report an absolute score anywhere in this repo. Every number is a
delta against a control I ran myself under identical conditions**, because that
is the only claim the setup supports.

For a sense of how hard the domain is, here is Sierra's
[τ³-Banking leaderboard](https://taubench.com/leaderboard?benchmark=knowledge),
checked on 2026-09-09:

| Model | Retrieval | Pass^1 |
|---|---|---|
| Qwen 3.8 Max | `alltools` | 55.2% |
| Claude Opus 5 | `alltools` | 48.7% |
| GPT-5.5 xhigh | `alltools` | 44.6% |
| GPT-5.2 high | `alltools` | 32.2% |
| GPT-5.2 high | static embeddings | 12.6% |

Those last two rows are the same model. Retrieval strategy moves it by 2.5x,
which is a bigger swing than most of the distance between models on the board.

Four reasons my 0.400 cannot go on that table. It is a tuning-set number and
theirs covers the full domain. I run BM25 at `top_k` 10, which is the weaker
static regime in the rows above, while nearly every board entry uses agentic
search. Every board entry also uses `gpt-5.2` as the user simulator where I use
the same Qwen that plays the agent, and a different simulated customer means a
different task difficulty. And the benchmark version differs: mine is tau2-bench
v1.0.1 at `fc0055dc`, the board is τ³-Banking after a round of task fixes and a
full re-run.

None of those four affect a within-setup delta, which is why the delta is what I
report.

One more thing on cost, since it cuts against me. Qwen3.8-27B runs at $0.42 and
$3.00 per million tokens, which puts it at the 59th percentile of 364
tool-capable models on OpenRouter. Several closed models are cheaper, including
GPT-5.6 Luna at $0.20 and $1.20. Open weights and cheap inference are not the
same thing.

## How it works

The harness is plain text appended to the agent's system prompt inside a
`<harness_rules>` block, and that is the entire intervention. No fine-tuning and
no weight changes. The environment, meaning tools, knowledge base, retrieval
breadth, step limit, scorer and user simulator, is identical in every arm.

tau2-bench is pinned at a commit and cloned rather than vendored, so the
benchmark stays byte-identical and independently checkable. The agent variant
registers itself on tau2's registry at runtime instead of patching its source.

One fixer iteration goes: build a digest for each task containing the customer's
goal and the ordered trace of every tool call and response, with errors included
and repeats flagged, then make a single model call that returns a diagnosis and a
rewritten rules section, apply it verbatim, run all ten dev tasks at three trials,
and keep it only if the mean improves by at least 0.10. Chaining between
iterations is automatic. No human picks the inputs.

The model chooses one failure category per iteration from six: `search_timing`,
`search_coverage`, `search_precision`, `tool_sequencing`, `reasoning` and
`action`. It picked `tool_sequencing` twice and never once picked either of the
retrieval-timing categories, which lines up with what the failure analysis found
independently.

The rule I held myself to throughout: **a human may author the method, but a
human never authors the artifact under test.** The fixer starts from an empty file, is
blocked in code from writing the frozen v0 rules, never sees held-out tasks or
the evaluation criteria, and asserts that the agent loaded the exact file it
edited before any money is spent. Probes have to demonstrate a delta against
control rather than just showing a feature is switched on, a rule I added after
my first reasoning probe passed while testing nothing at all.

### Step-budget awareness

tau2's step counter lives on the orchestrator and the agent cannot see it, so it
works to a deadline it has no way to read. Across 79 executions that hit the
50-step cap, the agent's own turn count at termination was consistently 26 with a
standard deviation of 1.3, which makes 26 a usable proxy. Injecting that each
turn as a `<step_budget>` block is the whole change. It is agent scaffolding
rather than a harness edit: the rules file is untouched, and with the toggle off
the agent is byte-identical to the harness-only configuration.

## The harness the model wrote

Every line of [`harness/rules_fixer.md`](harness/rules_fixer.md) was written by
the model starting from an empty file. Two of the seven rules:

> Debit card lost/frozen: freeze immediately. If the customer wants the card
> closed/replaced, a FROZEN card must be unfrozen before `close_debit_card`;
> then close and order the replacement. Do not retry `close_debit_card` while
> the card is FROZEN.

> No duplicate calls: do not call the same tool with the same arguments again
> unless the previous call failed.

The first one is the model working out the freeze-before-close ordering error
from a raw trace on its own. That bug cost roughly nine steps of a fifty-step
budget on one task.

[`docs/sample-transcripts.md`](docs/sample-transcripts.md) has all ten tasks from
one full trial if you want to see what the agent actually does, including what
the scorer wanted against what it did on the failures.

## Reproduction

```bash
./scripts/setup_env.sh                         # clones tau2-bench at the pin
./scripts/run_eval.sh task_001                 # no-harness baseline

STEP_BUDGET=26 TRIALS=3 RULES=rules_fixer.md \
  AGENT=llm_agent_harness RUNNER=python \
  ./scripts/run_eval.sh task_002 task_025 task_036 task_039 task_052 \
                        task_053 task_067 task_075 task_077 task_090
```

Needs `OPENROUTER_API_KEY`. In practice I run everything through the `tau2-eval`
workflow, because my dev sandbox blocks the model provider. Runs that produce no
signal are rejected by [`scripts/check_results.py`](scripts/check_results.py)
before anything lands, which matters because tau2 exits 0 even when every task
fails with an infrastructure error.

## Limitations

The 0.400 is a development-set result and the harness was tuned against those ten
tasks. The held-out gain was 0.100 at one trial, inside the noise floor, so it
neither confirms nor refutes the dev result.

Ten tasks is not many. Even at three trials a one-task move is directional. The
step budget on its own is worth 0.067, below my own gate, so only the full stack
clears it. One model, one domain, five fixer iterations, one keeper.

Cache and cost figures are recorded per message by the runner rather than
reconciled against an invoice.

One pathology I reported early on, "phantom duplicate accounts," turned out to be
my own analysis error and is corrected in
[`harness/FAILURE_ANALYSIS.md`](harness/FAILURE_ANALYSIS.md).

## What I would do next

Three trials on the held-out set, which is the run that resolves the open
question, at roughly $12.

Move the step budget into a trailing message to keep the accuracy gain while
restoring the cache discount. Ten lines or so, and it halves the cost of every
run after it.

A router that classifies the request and loads only that workflow's rules. Four
of the seven model-authored rules are already per-workflow procedures, and the
one regression that hurt most came from a global checklist sitting above rules
that already worked, which is exactly the failure routing would prevent.

I would not build the progress-gated loop-breaker I originally had ranked highly.
Five of the seven remaining non-convergent runs are on tasks that score zero even
in the trials where they do converge, so its realistic ceiling is about 0.067.
See [`harness/FUTURE_OPTIONS.md`](harness/FUTURE_OPTIONS.md).

## Repository map

| Path | What it is |
|---|---|
| [`harness/rules_fixer.md`](harness/rules_fixer.md) | the model-authored harness |
| [`harness/rules.md`](harness/rules.md), [`harness/rules_v1.md`](harness/rules_v1.md) | frozen v0 harness and a human-written control |
| [`harness/agent_harness.py`](harness/agent_harness.py) | the agent variant, plus step-budget injection |
| [`harness/fixer.py`](harness/fixer.py) | the loop: digest, diagnose, rewrite, evaluate, keep or revert |
| [`harness/FIXER_SPEC.md`](harness/FIXER_SPEC.md) | loop design, the v1 to v2 defect table, disclosures |
| [`harness/FAILURE_ANALYSIS.md`](harness/FAILURE_ANALYSIS.md) | failures classified against trajectory evidence |
| [`harness/fixer_v2_log.md`](harness/fixer_v2_log.md), [`harness/fixer_log.md`](harness/fixer_log.md) | every iteration's diagnosis, diff and outcome |
| [`configs/`](configs/) | frozen model controls, and the dev, test and holdout task sets |
| [`results/`](results/) | all 21 scored runs, committed by CI, never edited by hand |
| [`scripts/`](scripts/), [`.github/workflows/`](.github/workflows/) | environment pin, runner, signal gate, CI |
| [`docs/sample-transcripts.md`](docs/sample-transcripts.md) | ten full conversations from one trial |
