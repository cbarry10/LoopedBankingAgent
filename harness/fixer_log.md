# Fixer change log

One entry per fixer iteration. See harness/FIXER_SPEC.md.

## Iteration 1 — category: search_precision — kept: False
- baseline: 2/10 (mean 0.20)
- candidate: 1/10 (mean 0.10)
- outcome: reverted (no strict improvement: 0.10 <= 0.20)
- change: Strengthen the search-precision rule to require exact product/account/card names with segment and object-type qualifiers and to treat mismatched documents as missing facts.
- diagnosis: In multiple failed tasks the agent searched repeatedly but retrieved documents for the wrong product, segment, or account type: task_002 queries for personal Platinum Rewards Card kept returning business_gold_rewards_card, silver, or general docs; task_067 queries for Platinum Plus, Diamond Elite, and Gold Plus savings returned general, business, or card docs; task_075 queries for Bluest and Purple checking fees returned business, savings, or other checking docs; task_090 searches for the debit card PIN unlock tool returned unrelated general or credit card docs. This recurring query-precision failure caused unsupported actions or step exhaustion, rather than a simple lack of searches.

```diff
--- rules.md (before)
+++ rules.md (after)
@@ -10,10 +10,15 @@
    on one from memory or assumption.
 
 2. **Search precisely.** Query for the single specific fact you are missing,
-   using the customer's concrete terms — the product name, the action, the
-   exact figure or condition in question. Prefer one narrow query over a broad
-   one. If a result lacks the fact, refine the query with different keywords
-   rather than repeating the same search.
+   using the exact product, account, or card name in quotes plus the customer's
+   segment and object type (for example, "personal Platinum Rewards Card",
+   "business Platinum Rewards Card", "Bluest Account checking", "debit card
+   PIN unlock"). Do not lead with generic terms such as "highest", "best",
+   "options", "comparison", or "internal tool", and do not use KB_search to
+   discover tool names or schemas; first identify the exact product, account,
+   card, or action, then search one narrow fact at a time. If a retrieved
+   document is for a different product, segment, or object type, treat it as
+   not containing the needed fact and refine the query rather than using it.
 
 3. **Re-search only on new information.** Do not repeat a search you have
    already run. Search again only when the customer introduces new information,
```

## Iteration 2 — category: action — kept: False
- baseline: 2/10 (mean 0.20)
- candidate: 1/10 (mean 0.10)
- outcome: reverted (no strict improvement: 0.10 <= 0.20)
- change: Add a strict action gate requiring exact retrieved support for the intended action, product, and account/card type before acting, and requiring immediate action once that support is present.
- diagnosis: The most important recurring failure is taking an account action that is not supported by the exact retrieved policy or that mismatches the account/card type. In task_002 the agent applied for a Gold Rewards Card after searching mainly Platinum, Diamond, and Silver documents, with no retrieved Gold personal-card terms. In task_075 it opened a Bluest Account without retrieving Bluest ATM-fee terms. In task_077 it used a credit-card replacement tool for lost debit cards. In task_053 it approved a Silver Rewards Card limit increase after the Silver tier requirement search was still pending. In task_039 it filed many disputes with the same card action without retrieved support for each dispute reason. In task_090 it found the PIN-unlock policy/tool but did not execute the supported action before running out of steps.

```diff
--- rules.md (before)
+++ rules.md (after)
@@ -9,7 +9,7 @@
    eligibility, or limits, call `KB_search` first. Never state a policy or act
    on one from memory or assumption.
 
-2. **Search precisely.** Query for the single specific fact you are missing,
+2. **Search precisely.** Query for the specific fact you are missing,
    using the customer's concrete terms — the product name, the action, the
    exact figure or condition in question. Prefer one narrow query over a broad
    one. If a result lacks the fact, refine the query with different keywords
@@ -20,11 +20,18 @@
    or when you reach a new decision that needs a fact you have not yet
    retrieved. Once you hold the fact you need, act on it — do not keep searching.
 
-4. **Act only on retrieved evidence.** Take an account action, or state a
-   policy as fact, only when a KB document you have retrieved supports it.
-   Name the supporting policy in your reasoning before you act. If the KB does
-   not contain the needed information, tell the customer you cannot confirm it
-   rather than guessing.
+4. **Action gate: exact support before acting.** Before any state-changing
+   account action, product application, or recommendation that selects a
+   specific product/account, check that a retrieved KB document explicitly
+   supports that exact action for the exact account/card type and the
+   customer's stated condition. The support must match the intended option
+   (e.g., debit vs. credit, personal vs. business, the named card/account,
+   the requested limit, fee, or dispute reason). A document about a different
+   product, tier, account type, or action is not sufficient. If the exact
+   support is missing, search for it; if it remains unavailable, tell the
+   customer you cannot confirm or perform that action rather than guessing.
+   If the exact support is present, take the action promptly and do not add
+   extra searches or steps.
 
 When you have the evidence and have completed the customer's request, stop —
 do not take extra steps.
```
