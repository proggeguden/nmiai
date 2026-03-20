# Astar Island: One Self-Improvement Iteration

Make ONE targeted change to predictor.py, test it, and commit if it improves backtest KL.

## Steps

### 1. Diagnose: Read latest backtest results
- Read `astar-island/baseline.json` (or run backtest if missing)
- Look at:
  - `per_terrain_kl`: which terrain has highest `share_of_loss`?
  - `worst_cells`: what bucket keys appear repeatedly? What's predicted vs actual?
  - `per_round`: which rounds are worst? (high KL = harsh conditions)
  - `model_variants`: is Sp+Forward better or worse than Spatial?
- Read `astar-island/predictor.py` to understand current logic

### 2. Hypothesize: Pick ONE change
Choose the change with highest expected impact. Categories:
- **Parameter tuning**: Adjust smoothing K per terrain, shrink thresholds, calibration strengths, clamp bounds
- **Bucket refinement**: Add/modify spatial feature to split a high-error bucket
- **Calibration step**: New post-model adjustment (e.g., winter severity, expansion modulation)
- **Feature engineering**: New spatial feature in compute_feature_map

Rules:
- ONE change per iteration (isolate the effect)
- Target the terrain/bucket with highest KL share
- Keep it simple — parameter tweaks before structural changes
- Don't re-try changes that already regressed (check git log)

### 3. Implement: Edit predictor.py
- Make the change
- Keep it minimal — don't refactor surrounding code

### 4. Fast gate: Unit + integration tests
Run: `cd /Users/jakobtiller/Desktop/nmiai/code/nmiai/.claude/worktrees/astar-island/astar-island && pytest test_predictor_unit.py test_predictor_integration.py -x --tb=short`
- Must pass (exit 0). If fails → fix or revert.
- Takes <1 second.

### 5. Backtest gate: Regression detection
Run: `cd /Users/jakobtiller/Desktop/nmiai/code/nmiai/.claude/worktrees/astar-island/astar-island && python3 test_backtest.py --output results_improve.json --baseline baseline.json --threshold 0.10`
- Exit 0 = no regression → proceed
- Exit 1 = regression → revert the change, try a different approach
- Takes ~30 seconds

### 6. Evaluate results
Read `results_improve.json` and compare to baseline:
- Overall avg KL: improved or same?
- Per-round: any round regressed >10%?
- Per-terrain: did the target terrain improve?

### 7. If improved (no regression):
```bash
cd /Users/jakobtiller/Desktop/nmiai/code/nmiai/.claude/worktrees/astar-island/astar-island
cp results_improve.json baseline.json
git add predictor.py baseline.json
git commit -m "Improve: [description of change] (KL X.XXXX → Y.YYYY)"
```

### 8. If regressed:
- Revert the change: `git checkout -- predictor.py`
- Report what was tried and why it regressed
- Suggest a different approach for the next iteration

### 9. Record findings
**Always** update `PLAN.md` with what was tried and the result — even (especially) if it failed or was neutral. Add to the "What we tried and learned" section or create a new subsection. This prevents re-trying dead-end approaches and builds institutional knowledge.

Format:
```
### [Step number]. [Description] [status emoji: ✅/❌/➖]
- What: [1-line description of change]
- Result: [KL before → after, which rounds improved/regressed]
- Why it worked/failed: [1-line explanation]
```

## Output
Report:
- What was changed and why
- Before/after KL (overall and target terrain)
- Whether committed or reverted
- Suggestion for next iteration

## Important
- Working directory: `/Users/jakobtiller/Desktop/nmiai/code/nmiai/.claude/worktrees/astar-island/astar-island`
- Use `python3 -m pytest` (not bare `pytest`) for test commands
- Check `git log --oneline -10` before choosing a change — don't repeat failed approaches
- Check PLAN.md "What we tried and learned" section — don't repeat failed approaches listed there
- Each iteration should be independent — start fresh from current baseline
- If 3 consecutive iterations show no improvement, consider a structural change instead of parameter tuning

## Known dead ends (DO NOT retry)
- **Stronger forest entropy injection**: Increasing shrink max/multipliers causes R2 regression (+24.9%). The blunt shrink hurts moderate rounds where forest actually stays. Needs per-round conditioning, not global strength increase.
- **Forest smoothing K reduction (4→2)**: Zero effect in backtest — buckets have hundreds of observations so K barely matters (n/(n+4) ≈ n/(n+2)). Only relevant in production with sparse queries.
- **4-level distance buckets**: Fragments data, consistently hurts (from Phase 3)
- **Forward model (Sp+Forward)**: Consistently worse than pure Spatial model across all rounds
