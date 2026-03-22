# Round 34: Fix All Known Remaining Issues

> **For agentic workers:** REQUIRED: Use superpowers-extended-cc:subagent-driven-development (if subagents available) or superpowers-extended-cc:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all known bugs and improvements identified by our research agents in a single deploy.

**Architecture:** Changes span agent.py (executor error handling, replan, persona selection) and generic_tools.py (analyze_response error detection). No new files.

**Tech Stack:** Python, Gemini Flash for replan

---

## Files to Modify

| File | Changes |
|------|---------|
| `agent.py` | Error result normalization, single-attempt replan, smart persona selection |
| `generic_tools.py` | analyze_response error detection |

---

### Task 1: Error result normalization — prevent status-code-as-ID leaks

**Why:** When step N fails with 422, the raw error `{"status": 422, "message": "..."}` is stored. Then `$step_N.id` resolves to... nothing (no `id` key). But `$step_N.status` resolves to `422`. If the planner wrote `$step_N.id` and the resolver falls through, downstream steps might silently use wrong values.

**Files:** `agent.py` — the error storage path (~line 1771)

- [ ] **Step 1:** Mark error results so the resolver can detect them. In the error storage path, add `_error: True` to the stored dict:
```python
# Current: results[f"step_{step['step_number']}"] = parsed
# Change to:
parsed["_error"] = True
results[f"step_{step['step_number']}"] = parsed
```

- [ ] **Step 2:** In `_resolve_placeholder`, when traversing a result that has `_error: True`, return `_UNRESOLVED` immediately instead of walking into the error dict:
```python
# At the start of path resolution, after fetching obj = results[result_key]:
if isinstance(obj, dict) and obj.get("_error"):
    return _UNRESOLVED
```

- [ ] **Step 3:** Verify: `python3 -c "from main import app; print('OK')"`

---

### Task 2: Single-attempt LLM replan on write failures

**Why:** When a write step gets 422 (wrong fields, missing data), the agent currently gives up. One replan attempt using Gemini Flash could fix the payload. The REPLAN_PROMPT already exists.

**Files:** `agent.py` — executor error handling path (~line 1770)

- [ ] **Step 1:** After the bank account handler and employee email handler, before the fail-fast path, add a single replan attempt for write calls only:

```python
# Only replan write failures (POST/PUT/DELETE), not GET (free)
# Only on 400/422 (not 403/404/500)
# Single attempt only (no retry loops)
if (
    status_code in RETRYABLE_STATUS_CODES
    and resolved_args.get("method", "").upper() in ("POST", "PUT", "DELETE")
    and step['step_number'] not in healed_steps
):
    # Use flash model for speed
    try:
        from prompts import FIX_ARGS_PROMPT
        fix_prompt = FIX_ARGS_PROMPT.format(
            method=resolved_args.get("method"),
            path=resolved_args.get("path"),
            query_params=json.dumps(resolved_args.get("query_params", {})),
            body=json.dumps(resolved_args.get("body", {}), default=str)[:3000],
            error_response=result_str[:1000],
            endpoint_schema="(see API reference)",
            common_errors="(none)",
        )
        fix_response = heal_llm.invoke([HumanMessage(content=fix_prompt)])
        fix_raw = _extract_text(fix_response.content)
        fixed_args = json.loads(fix_raw)  # parse the corrected args

        # Retry with fixed args
        retry_result = tool.invoke(fixed_args)
        retry_error, retry_status = _is_api_error(retry_result)
        if not retry_error:
            parsed = json.loads(retry_result)
            results[f"step_{step['step_number']}"] = _normalize_result(parsed)
            healed_steps.append(step['step_number'])
            completed.append(step['step_number'])
            log.info(f"Step {step['step_number']} healed via replan")
            return { ... success state ... }
    except Exception as e:
        log.warning(f"Replan failed: {e}")
        # Fall through to fail-fast
```

- [ ] **Step 2:** Verify: `python3 -c "from main import app; print('OK')"`

---

### Task 3: Smart persona selection by task complexity

**Why:** Random selection wastes submissions on suboptimal personas. Simple tasks need precise (temp=0), complex ones benefit from thorough (temp=0.3).

**Files:** `agent.py` — planner node (~line 1234)

- [ ] **Step 1:** Replace random.choices with task-aware selection:

```python
import random
prompt_lower = state["original_prompt"].lower()

# Simple tasks → precise (temp=0, deterministic)
simple_keywords = ["create customer", "create product", "department", "supplier",
                   "kunde", "produkt", "avdeling", "leverandør", "client", "produit",
                   "Kunde", "Produkt", "Abteilung", "fournisseur", "producto"]
# Complex tasks → thorough (temp=0.3)
complex_keywords = ["project", "lifecycle", "payroll", "salary", "year-end",
                    "month-end", "reconcil", "prosjekt", "lønn", "årsoppgj"]

if any(kw in prompt_lower for kw in simple_keywords):
    profile = PLANNER_PROFILES[0]  # precise
elif any(kw in prompt_lower for kw in complex_keywords):
    profile = PLANNER_PROFILES[1]  # thorough
else:
    # Default: weighted random for unknown task types
    profile = random.choices(PLANNER_PROFILES, weights=[60, 30, 10], k=1)[0]
```

- [ ] **Step 2:** Verify: `python3 -c "from main import app; print('OK')"`

---

### Task 4: Detect analyze_response errors in executor

**Why:** When analyze_response returns `{"error": "..."}`, the executor treats it as success. Downstream `$step_N.fieldName` resolves to None silently.

**Files:** `agent.py` — executor success path (~line 1660)

- [ ] **Step 1:** After json.loads succeeds on a tool result, check for analyze_response error:

```python
if tool_name == "analyze_response" and isinstance(parsed, dict) and "error" in parsed:
    log.warning(f"Step {step['step_number']}: analyze_response returned error: {parsed['error'][:200]}")
    parsed["_error"] = True
    results[f"step_{step['step_number']}"] = parsed
    error_count += 1
    completed.append(step["step_number"])
    return { ... error state ... }
```

- [ ] **Step 2:** Verify: `python3 -c "from main import app; print('OK')"`

---

### Task 5: Smoke test, commit

- [ ] **Step 1:** Full verification:
```bash
python3 -c "from main import app; print('OK')"
python3 -c "from prompts import PLANNER_PROMPT; PLANNER_PROMPT.format(today='2026-03-22', tool_summaries='test', task='test'); print('Prompt OK')"
```

- [ ] **Step 2:** Commit:
```bash
git add agent.py generic_tools.py
git commit -m "Round 34: Error normalization + single replan + smart persona + analyze error detection"
```
