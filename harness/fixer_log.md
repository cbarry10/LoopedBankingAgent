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
