# Astar Island: Analyze Scores & Identify Improvements

Deep analysis of competition scores, error patterns, and simulation dynamics to identify frontier improvement opportunities.

## Steps

1. **Fetch scores**: Run `cd /Users/jakobtiller/Desktop/nmiai/code/nmiai/.claude/worktrees/astar-island/astar-island && python3 test_local.py --my-rounds`

2. **Fetch leaderboard**: Run `cd /Users/jakobtiller/Desktop/nmiai/code/nmiai/.claude/worktrees/astar-island/astar-island && python3 test_local.py --leaderboard`

3. **Build score table**: For each round with a score, compute:
   - Weight = `1.05 ^ round_number`
   - Weighted score = raw score × weight
   - Best weighted score (our leaderboard score)

4. **Run backtest**: Run `cd /Users/jakobtiller/Desktop/nmiai/code/nmiai/.claude/worktrees/astar-island/astar-island && python3 test_backtest.py --output /tmp/astar_analyze_results.json --baseline baseline.json`
   - This takes ~30s, backtests all completed rounds

5. **Deep analysis**: Read `/tmp/astar_analyze_results.json` and analyze at multiple levels:

   **Level 1 — Error decomposition**:
   - Per-terrain KL shares across rounds: is Plains always dominant or does it vary?
   - Per-round variation: correlate KL with forward_rates (survival, expansion). Which hidden params drive error?
   - Worst cells: cluster by bucket key. Are the same buckets consistently bad?

   **Level 2 — Simulation mechanics analysis**:
   - Map error patterns to simulation phases. High Plains error near settlements = Growth phase expansion mismatch. High Forest error = Environment phase reclamation mismatch.
   - Check: does the model handle bimodal outcomes? (A settlement either expands or doesn't — the true distribution may be a mixture, not a single mode)
   - Cross-round calibration: plot (conceptually) predicted vs actual probabilities. Are we systematically over/under-confident?

   **Level 3 — Competition gap analysis**:
   - Read competition docs using nmiai MCP tools for any rules or scoring nuances we're missing
   - Estimate: what raw score do top teams achieve per round? (Their weighted/weight ≈ raw score)
   - What modeling approach could bridge a 5-10 point gap? (ensemble? spatial smoothing? better calibration?)

6. **Output analysis report**:
   ```
   ## Score Table
   Round | Raw Score | Weight | Weighted | Rank

   ## Current Leaderboard Position
   Our best weighted: X (rank #Y)
   Gap to #1: Z points
   Top team estimated raw score: ~X per round

   ## Error Decomposition
   ### By terrain (averaged across rounds)
   Terrain    | KL    | Share  | Dominant error pattern

   ### By round condition
   Round | KL    | Survival | Expansion | Key error driver

   ### Worst bucket keys (cross-round)
   Bucket | Avg KL contribution | Predicted | Actual | Simulation explanation

   ## Frontier Improvement Opportunities
   Ranked by expected KL reduction, with theoretical justification:
   1. [Approach] — why it should work (simulation/statistical reasoning)
      Expected impact: KL reduction X → score improvement Y
   2. ...

   ## Projection
   If we improve KL by X on round N (weight W):
   New weighted score = ...
   New rank ≈ ...
   ```

## Important
- Working directory: `/Users/jakobtiller/Desktop/nmiai/code/nmiai/.claude/worktrees/astar-island/astar-island`
- Go beyond surface-level numbers — understand WHY errors occur through simulation mechanics
- Think about what top teams might be doing differently (spatial smoothing, ensembles, better calibration)
- Use nmiai MCP server tools to check competition docs for any scoring details or rules we're missing
