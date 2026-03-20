# Tripletex Agent — Iteration Roadmap

**Goal:** World-class score (correctness × efficiency). Current baseline: functional agent, generic 2-tool system, planner/executor/self-heal pipeline.

## Current Architecture

```
Prompt → Planner (1 LLM call) → Executor (pure Python loop) → Self-heal (on 400/422) → Done
                                      ↓
                              call_api / lookup_endpoint
```

**Strengths:** single-LLM-call planning, recursive placeholder resolution, targeted self-heal, production logging, auto-generated endpoint catalog.

**Key constraint:** Every 4xx error and every extra API call reduces score. Perfect correctness unlocks 2x efficiency bonus.

---

## Tier 1 — High Impact, Low Effort

### 1.1 Plan Validation Layer
**File:** `agent.py` (after planner, before executor)

After the planner generates a JSON plan, validate it before execution:
- All `tool_name` values are in `[call_api, lookup_endpoint]`
- All `$step_N` references point to earlier steps (no forward refs)
- All paths start with `/`
- Required fields present for known endpoints (cross-check with catalog schemas)
- If validation fails, ask LLM to re-plan with specific error feedback (max 1 re-plan)

**Why:** Catches hallucinated endpoints, forward references, and missing fields before they become 4xx errors. Each prevented error is a direct scoring win.

### 1.2 Workflow-Specific Plan Templates
**File:** `prompts.py`

Add concrete, tested plan examples for the most common task categories:
- **Invoice creation**: exact step sequence with all required fields
- **Payment registration**: search → find invoice → get payment types → PUT /:payment
- **Employee creation**: POST with required department.id
- **Customer creation**: POST with address fields
- **Project creation**: find/create manager → POST project

These aren't rigid templates — they're few-shot examples that guide the planner toward proven step sequences. Extract them from successful test runs.

**Why:** Few-shot examples massively reduce planner errors on common tasks. The planner currently gets format examples but not domain-specific workflow examples.

### 1.3 Smarter Error Abort Logic
**File:** `agent.py`, `check_done` function

Currently aborts after 3 errors regardless of type. Improve:
- **Auth errors (401/403):** abort immediately (credentials broken, no recovery)
- **Not found (404):** continue (search may have zero results, next step creates it)
- **Conflict (409):** continue (entity already exists, may be fine)
- **Schema errors (400/422):** count toward limit (self-heal already tried)
- **5xx:** retry once with backoff, then skip step

**Why:** Some "errors" are informational (404 on search = doesn't exist yet). Aborting early throws away work that was already done correctly.

### 1.4 Bulk Endpoint Optimization
**File:** `prompts.py` (planner rules)

Add explicit planner instructions:
- When creating multiple entities of the same type, always use the `/list` bulk endpoint (POST with array body)
- Example: creating 3 departments → 1 POST `/department/list` instead of 3 POST `/department`
- Add rule: "If the prompt asks to create N things of the same type, plan a single bulk call"

**Why:** 3 calls → 1 call is a huge efficiency win. The rule exists (#6) but needs a concrete example to be reliable.

---

## Tier 2 — High Impact, Medium Effort

### 2.1 Response Validation (Post-Execution Check)
**File:** new node in `agent.py` StateGraph, or post-loop in executor

After all steps complete, do a lightweight validation:
- For "create X" tasks: verify the created entity ID exists in results
- For "register payment" tasks: verify the payment response shows success
- For "create + send invoice" tasks: verify both creation and send succeeded
- If critical step failed, attempt a recovery sequence

This is NOT a full re-run. It's a single check: "did the last critical step succeed?"

**Why:** Currently the agent returns `completed` even if the final important step failed. A check catches this.

### 2.2 Dynamic Self-Heal Context
**File:** `agent.py`, `_ask_llm_to_fix_args`

Currently self-heal gets the endpoint schema. Enhance with:
- The specific error from `api_errors.md` if it matches (known fix patterns)
- The results of previous successful steps (so LLM can reference created IDs)
- Common gotcha notes relevant to that endpoint

**Why:** Self-heal success rate is the biggest lever after plan quality. Richer context = better fixes.

### 2.3 Placeholder Resolution Hardening
**File:** `agent.py`, `_resolve_placeholder`

Current issues:
- No type coercion: `$step_1.value.id` returns string "123" when API expects int 123
- LLM fallback is expensive and sometimes hallucinates

Fix:
- After resolution, if value looks numeric, cast to int
- Add path validation: if `$step_N` result doesn't have the expected path, log a clear error instead of falling through to LLM
- Cache resolved placeholders per step (avoid re-resolving same reference)

**Why:** Type mismatches cause subtle 422 errors that self-heal struggles with because the "fix" is a type cast, not a field change.

### 2.4 Expand Test Suite
**File:** `md/test_prompts.json`, `test_local.py`

Current coverage: 8 prompts across 4 categories and 4 languages. Expand to:
- All 7 languages (add French, Portuguese, plus more Norwegian variants)
- All task categories (voucher, product, travel expense, order, delete, update)
- Edge cases: multi-step tasks, tasks with prerequisites, tasks referencing non-existent entities
- Use `/harvest-logs` to continuously add real submission prompts

Add validation to `test_local.py`: after each test, verify expected entities exist via GET calls.

**Why:** Can't improve what you can't measure. Broader test coverage catches regressions and reveals weak categories.

---

## Tier 3 — Medium Impact, Higher Effort

### 3.1 Parallel-Safe Credentials
**File:** `tools.py`

Replace module-level globals with `contextvars.ContextVar`:
```python
from contextvars import ContextVar
_base_url: ContextVar[str] = ContextVar('base_url')
_session_token: ContextVar[str] = ContextVar('session_token')
```

**Why:** Required if you ever run multiple submissions concurrently. Low urgency for Cloud Run (1 request per instance) but prevents nasty bugs.

### 3.2 Adaptive Planner (Learn from Errors)
**File:** `agent.py`, `prompts.py`

After a self-heal succeeds, inject the lesson back into the planner prompt for future runs:
- Maintain a small "lessons learned" section in the prompt (or a separate file)
- Auto-populated from successful self-heal patterns in `api_errors.md`
- Example: "When creating employees, always include department.id — the API requires it even though the schema marks it optional"

**Why:** Converts runtime fixes into permanent planning improvements. Closes the feedback loop.

### 3.3 File Attachment Intelligence
**File:** `main.py`

Currently files are appended as raw text. Improve:
- CSV: parse headers, detect if it's a list of entities to create (→ bulk endpoint)
- JSON: validate structure, extract entity type
- PDF: extract text, summarize with 1 LLM call
- Pass structured summary to planner, not raw content

**Why:** File-based prompts are likely a task category. Better file parsing = better plans.

### 3.4 Request Timeout & Partial Recovery
**File:** `agent.py`, `main.py`

Add per-step timeout (30s default). If a step times out:
- Log it as a transient error
- Skip the step, continue with remaining steps
- If a critical step times out, retry once

Add a global timeout handler in main.py (Cloud Run gives 300s by default):
- If approaching timeout, execute remaining steps without self-heal (faster)

**Why:** Prevents hanging on slow LLM calls. Graceful degradation under time pressure.

---

## Iteration Protocol

For each iteration:

1. **Measure** — Run all prompts in `test_local.py`, note pass/fail per category
2. **Harvest** — `/harvest-logs` to pull real submission data
3. **Diagnose** — Review plans and errors: is the problem planning, execution, or self-heal?
4. **Fix** — Pick the highest-impact item from this plan
5. **Test** — Run affected test categories locally
6. **Deploy** — `gcloud builds submit` + `gcloud run deploy`
7. **Submit** — Run a real submission, harvest logs, compare scores
8. **Update** — Update this plan with results and next priorities

## Score Tracking

| Date | Submission | Correctness | Efficiency | Notes |
|------|-----------|-------------|------------|-------|
| | | | | (fill in after each scored submission) |
