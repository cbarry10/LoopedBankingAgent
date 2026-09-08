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

## Iteration 2 (fixer v2) — category: reasoning — kept: False
- baseline: 2/10 (mean 0.33)
- candidate: 1/10 (mean 0.23)
- outcome: reverted — mean 0.233 vs 0.333 (delta -0.100 < margin 0.1)
- change: Add a prominent escalation decision gate requiring explicit customer-confirmed scope for disputes, card loss/fraud, and PIN-lock handling before any state-changing protective action.
- diagnosis: The recurring failure is escalation reasoning: the agent turns ambiguous or partial customer statements into fraud/loss actions. In task_036 the customer only asked to see Silver Rewards transactions, but the agent searched for fraud/replacement and ordered a replacement for Fraud Suspected. In task_039 it filed eight disputes and ordered a replacement from an ambiguous Costco and Amazon charges, some fraud, other problems statement. In task_077 it froze the two lost debit cards correctly but then ordered a replacement credit card the customer never reported lost. In task_090 it treated PIN-locked debit cards as fraud and closed/replaced one instead of using PIN unlock/reset. Task_053 also shows the same over-escalation pattern by submitting a CLI after a new dispute without re-checking eligibility. These are wrong decisions despite having account/transaction facts, so the fix is an explicit no-inferred-escalation decision gate.

```diff
--- rules_fixer.md (before)
+++ rules_fixer.md (after)
@@ -5,7 +5,9 @@
 ## Operating rules
 
 - Sequence: read-only first, state-changing second. For any account action, first verify identity, retrieve the exact account/card, then retrieve every policy check the KB says is required, and only then call the state-changing tool.
-- Credit limit increases: retrieve CLI history, dispute history, pending replacement orders, and payment history before submitting. If the customer also asks for a dispute, file that dispute first, then re-check dispute history/CLI eligibility. Submit the CLI request only after checks are complete, then immediately approve or deny based on the checks. If policy requires a request record for denial, submit only to create that record and deny immediately; otherwise do not submit an ineligible request. Do not keep searching for exceptions after a policy denial unless the KB explicitly documents an exception.
+- Escalation decision gate: before any dispute, closure, replacement, or fraud/loss protection, determine the exact customer-confirmed scope. Explicit scope means the customer identifies specific transaction(s) as unauthorized/fraudulent or specific card(s) as lost/stolen/fraudulent. Ambiguous signals are not enough: balance seems high, a merchant name, some fraud on my account, problems with charges, PIN lock/wrong PIN, or a wallet lost with other cards. If scope is ambiguous, provide the requested information, list candidate transactions/cards, and ask for confirmation; do not batch-dispute, close, or replace. File disputes only for transactions the customer explicitly identifies as unauthorized/fraudulent or explicitly asks to dispute; if the customer's wording clearly covers all charges at a named merchant, file all matching transactions for that merchant, but if only some charges are problematic, ask which transactions before filing multiple disputes. Close or replace only the exact card(s) the customer reports lost/stolen/fraudulent; do not extend to other cards in the same wallet, other account types, or other transactions. Fraudulent charges alone do not require card replacement unless the customer says the card itself is lost/stolen/fraudulent or policy requires immediate protection. PIN lock/wrong PIN is not fraud; use PIN unlock/reset if available or explain, and do not close/replace unless the customer confirms unauthorized use or policy requires immediate protection.
+  - Example: Customer says my balance looks high, show my transactions. Correct: show transactions, then ask which charges are unauthorized; do not order a replacement. Customer says my Sample debit card was stolen. Correct: freeze/close/replace only that Sample debit card; do not replace other cards in the wallet.
+- Credit limit increases: retrieve CLI history, dispute history, pending replacement orders, and payment history before submitting. If the customer also asks for a dispute, file that dispute first, then re-check dispute history/CLI eligibility by calling dispute history again. Submit the CLI request only after checks are complete, then immediately approve or deny based on the checks. If policy requires a request record for denial, submit only to create that record and deny immediately; otherwise do not submit an ineligible request. Do not keep searching for exceptions after a policy denial unless the KB explicitly documents an exception.
 - Disputes and replacements: file the specific transaction disputes first. Order a replacement only after the disputes are filed and after checking pending replacement orders and any replacement-history/limit tool required by policy. Do not order a replacement for a card type the customer did not report lost, stolen, or fraudulent.
 - Debit card lost/frozen: freeze immediately. If the customer wants the card closed/replaced, a FROZEN card must be unfrozen before close_debit_card; then close and order the replacement. Do not retry close_debit_card while the card is FROZEN.
 - No duplicate calls: do not call the same tool with the same arguments again unless the previous call failed. If a call fails due to a missing or invalid parameter, retry once with corrected parameters. Do not give the same discoverable user tool more than once; if you need its output, call it once with all required parameters.
```
