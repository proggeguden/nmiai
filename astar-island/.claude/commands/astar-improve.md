# Astar Island: One Self-Improvement Iteration

Make ONE targeted change to predictor.py, test it, and commit if it improves backtest KL.

## Steps

### 0. Research: Think deeply before acting

Before jumping to parameter tweaks, **reason about the underlying simulation physics**. This is a stochastic cellular automaton with Norse civilisation dynamics. Think like a computational physicist:

- **Study the simulation phases** (Growth → Conflict → Trade → Winter → Environment). Each phase creates specific spatial patterns. What distributional signatures should each phase produce?
- **Analyze the error through the lens of the simulator**: If Forest cells near settlements show pred=89% Forest vs GT=73% Forest, what simulation mechanism causes forest clearing? (Expansion in Growth phase, or resource harvesting?) How does this interact with winter severity and settlement density?
- **Consider information-theoretic bounds**: The bucket model estimates P(final_state | initial_state, spatial_features). What features would be most informative? Think about mutual information — which features reduce entropy of the outcome distribution the most?
- **Study the per-round variation**: Rounds differ because of hidden parameters (winter severity, expansion rate, etc.). The model must generalize across these. Consider: are we over-fitting to average conditions and under-fitting to extreme rounds?
- **Think about calibration theory**: Platt scaling, isotonic regression, temperature scaling — are our post-model adjustments doing effective probability calibration, or are they ad-hoc?
- **Consider spatial correlation**: Nearby cells have correlated outcomes (a settlement expanding affects all adjacent cells). Are we treating cells as independent when they're not?

**Read the competition documentation** using the nmiai MCP server tools (`search_docs` / `list_docs`) for any rules or mechanics we might be missing.

**Read predictor.py thoroughly** — understand every post-model adjustment, every calibration step, every feature. Map out the full prediction pipeline mentally before proposing changes.

### 1. Diagnose: Read latest backtest results
- Read `astar-island/baseline.json` (or run backtest if missing)
- Read ALL per-round worst cells, not just one round — look for cross-round patterns
- Look at:
  - `per_terrain_kl`: which terrain has highest `share_of_loss`?
  - `worst_cells`: what bucket keys appear repeatedly? What's predicted vs actual?
  - `per_round`: which rounds are worst? (high KL = harsh conditions)
  - `model_variants`: is Sp+Forward better or worse than Spatial?
  - `forward_rates`: what do the per-round rates tell us about hidden parameter variation?
- Read `astar-island/predictor.py` to understand current logic in full

### 2. Hypothesize: Pick ONE change with theoretical justification

Choose the change with highest expected impact. Think beyond parameter tuning — consider:

**Modeling improvements** (highest potential):
- **Spatial correlation modeling**: MRF-inspired smoothing, neighbor-aware predictions
- **Mixture models**: The outcome distribution might be multimodal (settlement expands OR doesn't). A mixture of "expansion happened" and "no expansion" scenarios could reduce KL
- **Conditional calibration**: Different calibration per round-condition (harsh winter vs mild), estimated from observations
- **Better feature interactions**: Non-linear combinations of existing features (e.g., distance × cluster_density, coastal × forest_adj)
- **Hierarchical Bayesian**: Pool information across similar buckets with a learned prior, not just global prior

**Calibration improvements** (medium potential):
- **Beta calibration** or **Platt scaling** of bucket model outputs
- **Entropy-aware calibration**: Over-confident predictions (low entropy) should be shrunk more
- **Per-terrain temperature scaling**: Each terrain type may need different calibration temperature

**Feature engineering** (targeted):
- New spatial features based on simulation mechanics (e.g., food availability proxy, raid exposure)
- Derived features from settlement patterns (expansion frontier detection, cluster boundary cells)

**Rules:**
- ONE change per iteration (isolate the effect)
- Must have a theoretical reason — "I think this will work because [simulation mechanic / statistical principle]"
- Don't re-try changes that already regressed (check git log AND PLAN.md dead ends)
- Ambitious structural changes are OK if well-reasoned — don't limit yourself to parameter tweaks

### 3. Implement: Edit predictor.py
- Make the change
- Keep it minimal — don't refactor surrounding code
- Add a brief comment explaining the theoretical motivation

### 4. Fast gate: Unit + integration tests
Run: `cd /Users/jakobtiller/Desktop/nmiai/code/nmiai/.claude/worktrees/astar-island/astar-island && python3 -m pytest test_predictor_unit.py test_predictor_integration.py -x --tb=short`
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
- Did the change help the rounds/terrains you predicted it would? If not, why?

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
- Analyze: was the theory wrong, or was the implementation flawed?

### 9. Record findings
**Always** update `PLAN.md` with what was tried and the result — even (especially) if it failed or was neutral. Add to the "Overnight iteration findings" section.

Format:
```
- **[Description]** [✅/❌/➖]: [1-line description]. [KL before → after]. [Why it worked/failed].
```

## Output
Report:
- What was changed and why (with theoretical justification)
- Before/after KL (overall and target terrain)
- Whether committed or reverted
- What was learned about the model's behavior
- Suggestion for next iteration

## Important
- Working directory: `/Users/jakobtiller/Desktop/nmiai/code/nmiai/.claude/worktrees/astar-island/astar-island`
- Use `python3 -m pytest` (not bare `pytest`) for test commands
- Check `git log --oneline -10` before choosing a change — don't repeat failed approaches
- Check PLAN.md "Overnight iteration findings" section — don't repeat dead ends listed there
- Each iteration should be independent — start fresh from current baseline
- If 3 consecutive iterations show no improvement, consider a structural change instead of parameter tuning
- **Think like a competition winner**: the top teams likely use sophisticated calibration, spatial modeling, or ensemble methods. Don't settle for incremental parameter tuning when a structural insight could yield a step-change improvement.

## Known dead ends (DO NOT retry)
- **Stronger forest entropy injection**: Increasing shrink max/multipliers causes R2 regression (+24.9%). The blunt shrink hurts moderate rounds where forest actually stays. Needs per-round conditioning, not global strength increase.
- **Forest smoothing K reduction (4→2)**: Zero effect in backtest — buckets have hundreds of observations so K barely matters (n/(n+4) ≈ n/(n+2)). Only relevant in production with sparse queries.
- **4-level distance buckets**: Fragments data, consistently hurts (from Phase 3)
- **Forward model (Sp+Forward)**: Consistently worse than pure Spatial model across all rounds
