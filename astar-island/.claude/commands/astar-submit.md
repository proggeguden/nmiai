# Astar Island: Submit to Active Round

Check for active rounds and submit predictions if not already submitted.

## Steps

1. **Check rounds**: Run `cd /Users/jakobtiller/Desktop/nmiai/code/nmiai/.claude/worktrees/astar-island/astar-island && python3 -c "
import api_client, json
rounds = api_client.get_rounds()
my_rounds = api_client.get_my_rounds()
my_map = {r['round_number']: r for r in my_rounds}
for r in rounds:
    if r['status'] == 'active':
        rn = r['round_number']
        mr = my_map.get(rn, {})
        submitted = mr.get('seeds_submitted', 0)
        queries = mr.get('queries_used', 0)
        print(json.dumps({'active': True, 'round_id': r['id'], 'round_number': rn, 'seeds_submitted': submitted, 'queries_used': queries}))
        break
else:
    print(json.dumps({'active': False}))
"` to find the active round and check submission status.

2. **Decision logic**:
   - If no active round → report "No active round" and stop
   - If `seeds_submitted >= 5` AND `queries_used > 0` → already submitted, report status and stop
   - Otherwise → proceed to submit

3. **Submit**: Run `cd /Users/jakobtiller/Desktop/nmiai/code/nmiai/.claude/worktrees/astar-island/astar-island && python3 test_local.py --submit`
   - This runs the full pipeline: queries all seeds, builds predictions, submits all 5
   - main.py aborts safely if 0 observations (won't overwrite with garbage)

4. **Verify**: Run `cd /Users/jakobtiller/Desktop/nmiai/code/nmiai/.claude/worktrees/astar-island/astar-island && python3 test_local.py --my-rounds` to confirm submission

5. **Report**: Output a summary:
   - Round number and ID
   - Round weight: `1.05 ^ round_number`
   - Seeds submitted, queries used
   - If score available: raw score, weighted score = score × weight
   - Projected leaderboard impact

## Important
- Working directory is always: `/Users/jakobtiller/Desktop/nmiai/code/nmiai/.claude/worktrees/astar-island/astar-island`
- Never submit twice to the same round unless the model has been improved since last submission
- Rate limit: max 5 req/sec — the pipeline handles this
