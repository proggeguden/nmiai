# Round 25: Comprehensive Fix — All Known Issues

> **For agentic workers:** REQUIRED: Use superpowers-extended-cc:subagent-driven-development (if subagents available) or superpowers-extended-cc:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all identified failure patterns: silent failures from dummy/hardcoded data, ledger analysis compute capability, payroll employment detection, product double-creation, occupation code lookup, and planner guidance for complex task types.

**Architecture:** Changes span prompts.py (planner prompt rules + examples), agent.py (executor + validate_plan + meta-steps), and generic_tools.py (new analyze_response tool). No new files needed.

**Tech Stack:** Python, FastAPI, Gemini LLM, LangGraph

---

## Files to Modify

| File | Changes |
|------|---------|
| `prompts.py` | Remove hardcoded employee defaults, fix few-shot examples, add rules for payroll/reconciliation/analysis |
| `agent.py` | Add analyze_response executor capability for ledger analysis, fix occupation code handling, improve employment detection |
| `generic_tools.py` | Add analyze_response tool that uses LLM to extract structured data from API responses |

---

### Task 1: Fix silent failures — remove hardcoded employee defaults from prompt

**Why:** The prompt hardcodes `remunerationType: "MONTHLY_WAGE"`, `userType: "STANDARD"`, `dateOfBirth: "1990-01-01"`, and `department: "General"` which get copied verbatim instead of being extracted from the task. This causes 0 scores on tasks with different values.

**Files:**
- Modify: `prompts.py` line 77 (employee creation rule) and lines 119-127 (Example 1)

- [ ] **Step 1:** In the employee creation rule (line ~77), change from hardcoding values to instructing the planner to extract from the task:

Replace the line that says `ALWAYS use the 3-step chain: 1) POST /employee (firstName, lastName, email, dateOfBirth, userType: "STANDARD")` with:
```
ALWAYS use the 3-step chain: 1) POST /employee (firstName, lastName, email, dateOfBirth from task, userType from task — "STANDARD" for regular employees, "EXTENDED" if admin/kontoadministrator), 2) POST /employee/employment (employee:{id}, startDate from task), 3) POST /employee/employment/details (employment:{id}, date=startDate, employmentType/employmentForm/remunerationType/workingHoursScheme from task context — use MONTHLY_WAGE only if salary is described as annual/monthly, HOURLY_WAGE if hourly, NOT_CHOSEN if unspecified). Do NOT try to inline employments in the POST /employee body — it will be ignored.
```

- [ ] **Step 2:** In Example 1 (payroll), add a comment that the DOB is from the task, not a default. Also fix department to not always be "General":

The example should show the planner creating a department with a task-relevant name, not "General". But since this is a few-shot example and the task doesn't specify a department, keep "General" but add a note: `"description": "Create department (use task-specific name if given, otherwise 'General')"`

- [ ] **Step 3:** Verify prompt renders: `python3 -c "from prompts import PLANNER_PROMPT; PLANNER_PROMPT.format(today='2026-03-21', tool_summaries='test', task='test'); print('OK')"`

---

### Task 2: Fix product double-creation — planner POSTs even after GET finds product

**Why:** In Order→Invoice→Payment tasks, the planner GETs products by number (finds them) then POSTs them anyway → 422. The ternary fallback saves correctness but wastes 2 efficiency points per product.

**Files:**
- Modify: `prompts.py` (Example 5 and product rule)

- [ ] **Step 1:** Add a clear rule about conditional product creation:

Add to the product rule: `If you search for a product and find it (GET returns values), do NOT also POST it. Use the GET result directly. Only POST if GET returned empty.`

- [ ] **Step 2:** Simplify Example 5 — remove the POST /product step entirely and show GET-only pattern for existing products, with a note that POST is only needed when GET returns empty.

- [ ] **Step 3:** Verify: `python3 -c "from prompts import PLANNER_PROMPT; PLANNER_PROMPT.format(today='2026-03-21', tool_summaries='test', task='test'); print('OK')"`

---

### Task 3: Add analyze_response tool for ledger analysis tasks

**Why:** Ledger analysis tasks require computing "top 3 expense accounts with largest increase" from balance sheet data. The planner generates JavaScript expressions in placeholders that the executor can't resolve → 422 on project creation. We need a runtime LLM analysis step.

**Files:**
- Modify: `generic_tools.py` (add analyze_response tool)
- Modify: `agent.py` (register tool, handle in executor)
- Modify: `prompts.py` (add tool to available tools, add example)

- [ ] **Step 1:** In `generic_tools.py`, add an `analyze_response` tool:

```python
def analyze_response(previous_step_results: str, question: str) -> str:
    """Analyze data from previous API responses and return structured answers.

    Use this when you need to compute, filter, sort, or extract specific values
    from API response data (e.g., 'find the 3 accounts with the largest increase').

    Args:
        previous_step_results: JSON string of results from earlier steps
        question: What to compute/extract from the data

    Returns: JSON with the extracted/computed answer
    """
```

Implementation: call Gemini flash with the step results + question, parse the JSON response.

- [ ] **Step 2:** Register the tool in `agent.py`'s tool loading and handle `analyze_response` calls in the executor (similar to how `call_api` is handled but routes to the LLM instead of HTTP).

- [ ] **Step 3:** Add to planner prompt:
```
- **analyze_response**(previous_step_results, question): Analyze data from previous API call results. Use when you need to compute values, find top-N items, or extract specific data from responses. Returns JSON with the answer. Example: after GET /balanceSheet, use analyze_response to find "the 3 expense accounts with the largest increase between January and February".
```

- [ ] **Step 4:** Add a few-shot note in the Domain Knowledge section:
```
- **Ledger analysis tasks** ("find top 3 expense accounts", "analyze cost increases"): 1) GET /balanceSheet for each period, 2) Use analyze_response to compute the answer from the response data, 3) Use the computed values in subsequent steps (POST /project, etc.)
```

- [ ] **Step 5:** Verify: `python3 -c "from main import app; print('OK')"`

---

### Task 4: Fix payroll — employment detection for existing employees

**Why:** When the payroll task gives an employee email (meaning they exist), GET /employee finds them but GET /employee/employment returns empty because it needs `employeeId` filter. The planner then tries POST /employee/employment → 422 (already exists).

**Files:**
- Modify: `prompts.py` (payroll rule)

- [ ] **Step 1:** Update the payroll rule to fix employment detection:

```
- **Employee for payroll**: dateOfBirth REQUIRED. If employee already exists (GET found them), check employment with GET /employee/employment?employeeId=$step_N.values[0].id. If employment exists, use that employment's ID for salary transaction. If employment doesn't exist, create with the 3-step chain. salary/transaction specifications MUST have rate, count, AND amount.
```

- [ ] **Step 2:** Verify prompt renders.

---

### Task 5: Fix occupation code lookup

**Why:** GET /employee/employment/occupationCode returns empty list. The planner needs to search with correct params or skip occupationCode when it can't be found.

**Files:**
- Modify: `prompts.py` (employment details rule)

- [ ] **Step 1:** Update the employment details rule:

```
- **Employment details**: occupationCode is optional — do NOT look it up unless the task explicitly provides one. If the task specifies an occupation code number, use it directly as {"id": <number>}. If the task says "occupation code" without a number, omit it. Do NOT call GET /employee/employment/occupationCode — it often returns empty and breaks the plan.
```

- [ ] **Step 2:** Verify prompt renders.

---

### Task 6: Fix /:createReminder 422

**Why:** PUT /invoice/{id}/:createReminder returns 422. The prompt already has guidance but params may be wrong.

**Files:**
- Modify: `prompts.py` (reminder rule)

- [ ] **Step 1:** Check the endpoint catalog for createReminder params and verify our guidance matches.

- [ ] **Step 2:** Update the reminder rule if needed — ensure type, date, includeCharge, includeInterest are correct.

---

### Task 7: Smoke test, commit, deploy

- [ ] **Step 1:** `python3 -c "from main import app; print('OK')"`
- [ ] **Step 2:** Verify prompt: `python3 -c "from prompts import PLANNER_PROMPT; p = PLANNER_PROMPT.format(today='2026-03-21', tool_summaries='test', task='test'); print(f'Prompt: {len(p)} chars'); print('OK')"`
- [ ] **Step 3:** Commit: `git add agent.py prompts.py generic_tools.py && git commit -m "Round 25: Fix silent failures, add analyze_response, fix payroll/occupation/products"`
- [ ] **Step 4:** Deploy: `gcloud builds submit --tag gcr.io/ai-nm26osl-1788/tripletex && gcloud run deploy tripletex --image gcr.io/ai-nm26osl-1788/tripletex --platform managed --region europe-west1 --allow-unauthenticated --min-instances=3 --concurrency=1 --update-env-vars GEMINI_PLANNER_MODEL=gemini-3.1-pro-preview,GEMINI_MODEL=gemini-3-flash-preview`
- [ ] **Step 5:** Submit at https://app.ainm.no/submit/tripletex
