# Overnight Improvement Plan: 2026-03-22

**Current state:** 45.48 / 120 (37.9%), Rank ~#150. Target: top 10 (~92+ pts).
**Budget:** ~10 hours overnight. Focus on highest-ROI changes driven by log analysis.

---

## Diagnosis: Architectural Weaknesses

After reading every line of agent.py, prompts.py, generic_tools.py, tools.py, and main.py, these are the systemic issues -- not specific task bugs, but structural problems that cause failures across many tasks.

### 1. No adaptive error recovery (fail-fast is too aggressive)
The verifier is DISABLED. LLM self-heal (FIX_ARGS) is DISABLED. REPLAN is dead code.
When a write step fails (not a bank account or duplicate employee), the agent records the error and moves on. Downstream steps that depend on the failed step's ID cascade-fail via unresolved refs. One early failure can zero out an entire task.

This was the right call when self-heal was causing more harm than good. But the pendulum swung too far -- there is now zero recovery capability for anything outside two hardcoded patterns.

### 2. Multi-persona randomness adds variance without learning
The planner randomly picks precise (60%), thorough (30%), or creative (10%) on each submission. This means the same task gets a different plan quality each time purely by chance. On a best-score-kept system, variance is good IF you submit many times. But with limited submissions, you want consistency on easy tasks and exploration only on zero-score tasks.

### 3. analyze_response is an extra LLM call per use (slow + fragile)
Tasks that need data analysis (ledger analysis, balance sheet queries, top-N computation) route through analyze_response, which makes a separate Gemini call. This:
- Adds 2-5s latency per call
- Can fail (malformed JSON, timeout)
- Truncates input to 30K chars (may lose data)
- Returns JSON that must be parsed and referenced via $step_N -- another failure point

For complex analytical tasks (tasks 7, 12 -- both 0% or 15%), this is a bottleneck.

### 4. No per-task specialization
All 30 tasks go through the same planner prompt. The planner has no memory of what worked before. Tasks 9, 10, 11, 12, 16, 23, 30 are all zero-score -- the planner consistently generates wrong plans for these task types, and there is no mechanism to course-correct.

### 5. Placeholder resolution is fragile for multi-step chains
The _resolve_placeholder function handles $step_N.id well for simple cases but breaks on:
- $step_N references where step N returned an error (returns the error dict, not _UNRESOLVED)
- Nested references like $step_N.orderLines[0].id (works but only if normalization preserved the nested structure)
- References from analyze_response results (the response format varies)

For long plans (10+ steps), these cascade failures compound.

### 6. Scoring system interaction is not optimized
- GET is free but the agent doesn't exploit this enough. It could do a "verify" GET after every write to confirm the data landed correctly.
- 4xx errors on writes cost DOUBLE. The agent counts write errors but doesn't actively prevent them (beyond validate_plan's static checks).
- Best score per task is kept, but the agent doesn't know which tasks are already perfect and which need improvement.

---

## Tier 1: Highest Impact (Do First)

### 1A. Selective LLM replan for write errors (re-enable REPLAN on write failures)
**What:** When a write step gets 400/422, call _ask_llm_to_replan with the error context. The REPLAN_PROMPT and function already exist as dead code. Re-enable it with a single-attempt limit (no retry loops).
**Why:** Right now, a 422 on POST /employee/employment/details (e.g., wrong field name) kills the entire employee setup. One replan attempt could fix it. The infrastructure is already built and tested.
**Guard rails:** MAX_REPLANS=1 (not 3). Only on 400/422 (not 403/404/500). Only on write calls (GET failures are free). Log the replan decision.
**Risk:** LOW. The code already exists. Single attempt means no cascading retries. Fail-fast remains the default after one try.
**Effort:** ~30 lines changed in executor (un-comment replan path, add guards).
**Expected gain:** +5-10 points. Recovers partial failures on tasks 13, 17, 19, 20, 21, 22, 27 (all partially working, losing points to mid-plan errors).

### 1B. Task-type detection with workflow playbooks
**What:** Before planning, classify the task into a category (employee, invoice, payment, ledger-analysis, project, travel-expense, etc.) using keyword matching on the prompt. Then inject a task-specific "playbook" paragraph into the planner prompt with the known-correct step sequence.
**Why:** The planner prompt is generic. Tasks like "create employee" require a very specific 3-step chain (POST /employee, POST /employment, POST /employment/details) that the planner sometimes gets wrong. A playbook ensures the critical sequence is always correct.
**Implementation:** Add a `_detect_task_type(prompt)` function that returns a string. Add a `PLAYBOOKS` dict mapping task types to short instruction paragraphs. Inject `{playbook}` into PLANNER_PROMPT between the principles and the API constraints sections.
**Key playbooks to write:**
  - **employee**: 3-step chain with exact field mappings
  - **invoice-payment**: order -> invoice -> payment separation
  - **cancel-payment**: find existing invoice, reverse with negative paidAmount
  - **credit-note**: find existing invoice, createCreditNote
  - **custom-dimensions**: accountingDimensionName -> accountingDimensionValue -> voucher with freeAccountingDimension1
  - **ledger-analysis**: GET /ledger/posting with date range -> analyze_response
**Risk:** LOW. Playbooks are additive (injected into prompt, not replacing anything). The planner can still adapt -- playbooks are guidance, not constraints.
**Effort:** ~100 lines (detection function + 6-8 playbook strings).
**Expected gain:** +10-15 points. Directly targets tasks 9, 10, 16, 22, 23 (zero/near-zero scores with known solutions).

### 1C. Deterministic task-type routing for zero-score tasks
**What:** For the 3-4 task types where the planner consistently fails (custom dimensions, cancel payment, credit note), bypass the LLM planner entirely and use a hardcoded plan template. Fill in values with regex extraction from the prompt.
**Why:** These tasks have one correct workflow. The planner hallucinates wrong endpoints every time. A template guarantees at least partial credit.
**Guard:** Only use templates for task types where current score is 0%. Fall back to LLM planner if template can't extract needed values.
**Risk:** MEDIUM. Templates are brittle to prompt variation. Mitigate by keeping LLM fallback.
**Effort:** ~80 lines (3-4 template functions + value extraction).
**Expected gain:** +8-14 points. Tasks 23 (custom dimensions, +6), 16 (cancel payment, +4), 11 (multi-VAT, +4) are addressable.

---

## Tier 2: Medium Impact

### 2A. Verify-after-write pattern (free GET after every POST/PUT)
**What:** After each successful write step, automatically inject a GET to confirm the entity was created with correct values. Compare key fields against what was sent.
**Why:** GET is free. Silent write failures (200 status but wrong data) are invisible in current architecture. The scoring system checks field-by-field correctness -- if a field was silently dropped, we lose points without knowing.
**Implementation:** In executor, after a successful POST/PUT, construct a GET for the created entity with `fields=*` param. Log any mismatches as warnings.
**Risk:** LOW. GETs are free. Only risk is added latency (~200ms per verify). Don't do this if deadline is close.
**Effort:** ~40 lines in executor.
**Expected gain:** +3-5 points (catches silent field drops, informs future fixes).

### 2B. Smart persona selection instead of random
**What:** Replace random persona selection with task-type-aware selection:
  - Simple CRUD tasks (employee, customer, product) -> precise (temp=0)
  - Multi-step workflows (order->invoice->payment) -> thorough (temp=0.3)
  - Analytical tasks (ledger analysis, balance sheet) -> creative (temp=0.7)
**Why:** Random selection wastes 40% of submissions on suboptimal personas. Task-appropriate personas improve plan quality consistently.
**Risk:** LOW. Still uses the same planner code, just deterministic selection.
**Effort:** ~20 lines (switch statement in planner node).
**Expected gain:** +3-5 points (reduced variance on easy tasks, better plans on hard tasks).

### 2C. Improve analyze_response reliability
**What:** Three targeted fixes:
  1. Increase truncation limit from 30K to 60K chars (Gemini handles it fine)
  2. Add structured output format: tell the LLM to return `{"result": <value>}` specifically
  3. If analyze_response returns an error, retry once with simplified data (just the _all arrays, not full nested objects)
**Why:** Tasks 7 (ledger analysis, 15%) and 12 (ledger analysis, 0%) both depend on analyze_response. The current implementation loses data through truncation and returns unparseable results.
**Risk:** LOW. Backwards compatible.
**Effort:** ~25 lines.
**Expected gain:** +3-6 points (tasks 7, 12).

### 2D. Error result normalization fix
**What:** In executor, when a step fails with an API error, currently the raw error dict is stored as the step result (line 1771). This means `$step_N.id` on an error result returns the "status" field (an integer like 422) instead of _UNRESOLVED. Downstream steps then POST with `{"customer": {"id": 422}}`, which creates a 422 error.
**Fix:** Wrap error results in `{"error": ..., "_error": True}` and update _resolve_placeholder to return _UNRESOLVED when the result has `_error`.
**Why:** This is a silent cascade failure. The agent thinks it resolved the ref (it got an integer), but the integer is a status code, not an entity ID.
**Risk:** LOW. Only changes error path behavior.
**Effort:** ~15 lines.
**Expected gain:** +2-4 points (prevents cascade damage on partial failures).

---

## Tier 3: Nice to Have (If Time Permits)

### 3A. Efficiency optimization: strip unnecessary GETs from plans
**What:** The planner sometimes adds GET steps that don't feed into later steps (dead reads). After validate_plan, scan for GET steps whose $step_N is never referenced downstream. Remove them.
**Why:** While GETs are free for efficiency scoring, they add latency. On 250s deadline plans, saving 2-3 unnecessary GETs could prevent timeout.
**Risk:** LOW (removing unused GETs can't break anything).
**Effort:** ~20 lines.
**Expected gain:** +1-2 points (prevents occasional timeouts).

### 3B. Response caching for idempotent GETs
**What:** Cache GET responses by (method, path, sorted_params) within a single request. If the planner generates duplicate GETs (common in thorough mode), return cached result.
**Why:** Saves network round-trips. Some plans have 3-4 identical GET /employee searches.
**Risk:** LOW.
**Effort:** ~15 lines in tools.py.
**Expected gain:** +0-1 points (latency savings).

### 3C. Better prompt language detection
**What:** Detect prompt language and add a note to the planner: "This task is in [language]. Field values should use exactly the text from the task, not translated."
**Why:** The planner sometimes translates values (e.g., German department name -> English). Scoring checks exact field values.
**Risk:** LOW.
**Effort:** ~10 lines.
**Expected gain:** +1-2 points (prevents translation errors on non-English tasks).

### 3D. Pre-warm bank account + department + division on every request
**What:** Instead of injecting ensure_bank_account only when the plan has invoicing steps, always run the three ensure steps at request start. They're cheap (1-2 GETs each) and prevent errors later.
**Why:** Some tasks need a bank account but the planner doesn't generate /:invoice steps (e.g., payment tasks that use existing invoices). Missing bank account then causes a 422 mid-plan.
**Risk:** LOW. Adds ~500ms to every request but prevents downstream errors.
**Effort:** ~10 lines.
**Expected gain:** +1-2 points.

---

## Execution Order

```
Night 1 (22:00-02:00): Tier 1
  1B. Task-type detection + playbooks  (~100 lines, 1.5hr)
  1A. Re-enable single-attempt replan   (~30 lines, 30min)
  1C. Template routing for zero-score   (~80 lines, 1.5hr)
  Deploy + Submit + Harvest logs

Night 2 (02:00-06:00): Tier 2
  2D. Error result normalization fix     (~15 lines, 15min)
  2A. Verify-after-write                 (~40 lines, 30min)
  2B. Smart persona selection            (~20 lines, 15min)
  2C. analyze_response reliability       (~25 lines, 20min)
  Deploy + Submit + Harvest logs

Dawn (06:00-08:00): Tier 3 + iterate
  Fix anything broken from Tier 1/2
  3D. Pre-warm ensures                   (~10 lines, 10min)
  3C. Language detection                 (~10 lines, 10min)
  Final deploy + submit
```

## What NOT to Do

1. **No more few-shot examples in the prompt.** Round 26 removed them ("Principles over examples -- free the planner"). Adding them back constrains the planner's ability to adapt to novel tasks.

2. **No more validate_plan rules.** There are already 20+ rules. Each new rule risks breaking other tasks. The validate_plan function is 500 lines -- any change here needs very careful testing.

3. **No multi-attempt self-heal loops.** Round 21-24 proved these cause cascade failures. The single-attempt replan (1A) is the safe middle ground.

4. **No verifier re-enable.** The verifier's corrective steps corrupt $step_N refs and waste time. Keep it disabled.

5. **No prompt size increases.** The planner prompt is already ~15K chars. Adding more context risks hitting Gemini's quality cliff on long prompts.

6. **No dependency changes.** No new pip packages, no model changes, no infrastructure changes overnight.

## Score Projection

| Scenario | Points Added | New Total | Projected Rank |
|----------|-------------|-----------|----------------|
| Tier 1 only | +20-35 | ~70-80 | ~50-80 |
| Tier 1+2 | +30-50 | ~80-95 | ~20-40 |
| All tiers | +35-55 | ~85-100 | ~10-25 |

The realistic overnight target is **Tier 1 + most of Tier 2**, getting to ~80-90 points and top 30-40. Top 10 requires multiple submission cycles to iterate on remaining failures.
