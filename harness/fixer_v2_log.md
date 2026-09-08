# Fixer v2 change log

One entry per iteration. See harness/FIXER_SPEC.md (v2 section).

## Iteration 1 (fixer v2) — category: tool_sequencing — kept: True
- baseline: 1/10 (mean 0.20)
- candidate: 2/10 (mean 0.33)
- outcome: KEPT — mean 0.333 vs 0.200 (delta +0.133 >= margin 0.1)
- change: Add a tool-sequencing checklist requiring read-only eligibility checks before state-changing actions, no submit-then-deny, no duplicate calls, and unfreeze-before-close for lost debit cards.
- diagnosis: The dominant recurring failure is tool sequencing: the agent performs state-changing or redundant calls before completing required read-only checks, wasting the 50-step budget. In task_052 it submitted a CLI request before retrieving CLI history, dispute history, pending replacement orders, and payment history, then denied the request and searched for exceptions until max_steps; task_053 similarly submitted and approved a CLI before checking dispute/replacement/payment history and filed the dispute after the CLI. task_077 froze debit cards, then tried to close them while FROZEN, causing errors, unfreeze/close repeats, and an unnecessary credit-card replacement; task_036 repeated the same user tool and jumped to replacement instead of first showing transactions. The same pattern of redundant searches/calls appears in task_067, task_075, and task_090, where the agent loops on KB searches or duplicate lookups and never completes the requested account action.

```diff
--- rules_fixer.md (before)
+++ rules_fixer.md (after)
@@ -3,3 +3,11 @@
 Every line under the heading below was written by the fixer. No human-authored rules.
 
 ## Operating rules
+
+- Sequence: read-only first, state-changing second. For any account action, first verify identity, retrieve the exact account/card, then retrieve every policy check the KB says is required, and only then call the state-changing tool.
+- Credit limit increases: retrieve CLI history, dispute history, pending replacement orders, and payment history before submitting. If the customer also asks for a dispute, file that dispute first, then re-check dispute history/CLI eligibility. Submit the CLI request only after checks are complete, then immediately approve or deny based on the checks. If policy requires a request record for denial, submit only to create that record and deny immediately; otherwise do not submit an ineligible request. Do not keep searching for exceptions after a policy denial unless the KB explicitly documents an exception.
+- Disputes and replacements: file the specific transaction disputes first. Order a replacement only after the disputes are filed and after checking pending replacement orders and any replacement-history/limit tool required by policy. Do not order a replacement for a card type the customer did not report lost, stolen, or fraudulent.
+- Debit card lost/frozen: freeze immediately. If the customer wants the card closed/replaced, a FROZEN card must be unfrozen before close_debit_card; then close and order the replacement. Do not retry close_debit_card while the card is FROZEN.
+- No duplicate calls: do not call the same tool with the same arguments again unless the previous call failed. If a call fails due to a missing or invalid parameter, retry once with corrected parameters. Do not give the same discoverable user tool more than once; if you need its output, call it once with all required parameters.
+- Answer the explicit request first. If the customer asks to see transactions or account details, provide that information before taking optional fraud, replacement, or closure actions; do not infer fraud or cancel a card unless the customer confirms unauthorized charges or policy requires immediate protection.
+- Search discipline: stop KB searching once the exact fact needed for the next action is known. Do not re-search the same product/fact after a tool result or document already answers it. If a query returns an irrelevant document, reformulate the query; do not loop on near-identical searches.
```
