# Astar Island: Analyze Scores & Identify Improvements

Analyze our competition scores and identify the best improvement opportunities.

## Steps

1. **Fetch scores**: Run `cd /Users/jakobtiller/Desktop/nmiai/code/nmiai/.claude/worktrees/astar-island/astar-island && python3 test_local.py --my-rounds`

2. **Fetch leaderboard**: Run `cd /Users/jakobtiller/Desktop/nmiai/code/nmiai/.claude/worktrees/astar-island/astar-island && python3 test_local.py --leaderboard`

3. **Build score table**: For each round with a score, compute:
   - Weight = `1.05 ^ round_number`
   - Weighted score = raw score × weight
   - Best weighted score (our leaderboard score)

4. **Run backtest**: Run `cd /Users/jakobtiller/Desktop/nmiai/code/nmiai/.claude/worktrees/astar-island/astar-island && python3 test_backtest.py --output /tmp/astar_analyze_results.json`
   - This takes ~30s, backtests all completed rounds

5. **Read results**: Read `/tmp/astar_analyze_results.json` and analyze:
   - Overall avg KL
   - Per-round KL breakdown (which rounds are worst?)
   - Per-terrain KL shares (Plains ~55%, Forest ~35% — what changed?)
   - Worst cells: what bucket keys, what's the pattern?
   - Model variant comparison (Spatial vs Sp+Forward)

6. **Output analysis report**:
   ```
   ## Score Table
   Round | Raw Score | Weight | Weighted | Rank

   ## Current Leaderboard Position
   Our best weighted: X (rank #Y)
   Gap to #1: Z points

   ## Error Breakdown (from backtest)
   Terrain    | KL    | Share  | Trend vs baseline
   Plains     | 0.XXX | 55%   | ↑/↓/→
   Forest     | 0.XXX | 35%   | ↑/↓/→
   ...

   ## Top Improvement Opportunities
   1. [description] — expected KL reduction: X → projected score improvement: Y
   2. ...

   ## Projection
   If we improve KL by X on round N (weight W):
   New weighted score = ...
   New rank ≈ ...
   ```

## Important
- Working directory: `/Users/jakobtiller/Desktop/nmiai/code/nmiai/.claude/worktrees/astar-island/astar-island`
- Compare to baseline.json if it exists: `python3 test_backtest.py --output /tmp/astar_analyze_results.json --baseline baseline.json`
- Focus on actionable insights: what specific change would reduce KL the most?
