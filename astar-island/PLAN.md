# Astar Island — Roadmap

## Completed Work

### Phase 1: MVP Pipeline
- [x] Project scaffold (FastAPI, api_client, predictor, test_local)
- [x] Correct API endpoints (simulate, submit, my-rounds, my-predictions, analysis, leaderboard)

### Phase 2: Transition Model
- [x] P(final_class | initial_terrain_code) from observations
- [x] Per-cell blending: observed cells mix local counts with global model
- [x] Smart query allocation: skip static tiles, prioritize settlement-heavy areas

### Phase 3: Spatial Feature Model
- [x] Spatial bucketing: P(class | terrain_code, spatial_features)
- [x] 3-level Manhattan distance to nearest settlement (≤2, 3-4, 5+)
- [x] Coastal adjacency, adjacent forest/settlement for settlement/port cells
- [x] Multi-seed observation: 10 queries per seed across all 5 seeds
- [x] BFS-precomputed distances for efficiency
- [x] ~14 spatial buckets with fallback to global model if <10 observations

### Phase 3.5: Richer Features + Smoothing (Round 7 submission)
- [x] Graduated forest adjacency (0/1/2/3+) for settlements/ports
- [x] Forest adjacency for plains, empty, ruin cells
- [x] Settlement adjacency for forest, ruin cells
- [x] Coastal flag for settlements
- [x] Adaptive k per terrain type (settlements k=8, plains/forest k=3)
- [x] Bayesian bucket smoothing (K=5) blends sparse buckets towards global prior
- [x] Cross-seed query allocation proportional to settlement density
- [x] ~30 spatial buckets (up from 14)

### Backtest Results (5-seed spatial, weighted KL — lower is better)
| Round | Phase 3 (R6) | Phase 3.5 (R7) | Phase 4 (R8) | Phase 4f+g (cluster+stats) | Notes |
|-------|-------------|---------------|-------------|---------------------------|-------|
| 1     | 0.0671      | 0.0664        | 0.0632      | 0.0620                    | |
| 2     | 0.0500      | 0.0495        | 0.0468      | 0.0456                    | |
| 3     | 0.0747      | 0.0666        | 0.0690      | 0.0690                    | Harsh winter |
| 4     | 0.0396      | 0.0392        | 0.0384      | 0.0380                    | Best round |
| 5     | 0.0715      | 0.0706        | 0.0718      | 0.0700                    | |
| 6     | 0.0643      | 0.0641        | 0.0615      | 0.0608                    | |
| 7     | —           | 0.1506        | 0.1468      | 0.1416                    | Very harsh winter |
| **Avg** | **0.0612** | **0.0594**  | **0.0568** (R1-6) | **0.0576** (R1-6)   | |

### Key Insights
- **Hidden params are unique per round** — historical priors don't help, must learn fresh
- **Multi-seed observation beats single-seed** on 4/5 rounds (more diverse terrain coverage)
- **Distance-to-settlement is the strongest spatial feature** — settlement proximity drives expansion, food, and survival
- **Settlement survival ranges 2–44%** across rounds depending on hidden params
- **4-level distance buckets hurt** — fragments data too much, especially for harsh-winter rounds
- **Forest adjacency on empty cells helps a lot for harsh winters** (forest reclamation)
- **Bayesian smoothing helps more than hard min-obs threshold** — prevents overfitting sparse buckets

### Scoring Context
- Round 5: 13.1 (rank 130/144) — naive predictor
- Round 6: **78.5** (rank 28/186) — first spatial model
- Round 7: **60.4** (rank 83/199) — harsh winter, high expansion
- Round 8: **82.4** (rank 55/214)
- Round 9: 8.5 (rank 205/221) — broken submission
- Round 10: **82.0** (rank 60/238)
- Round 11: **79.7** (rank 61/171)
- Round 12: **59.4** (rank 38/146) — tough round
- Round 13: **73.2** (rank 126/186)
- Round 14: **74.1** (rank 71/244) — degraded by accidental resubmission
- Round 15: **86.1** (rank 97/262) — best raw score ever, weighted=179.0
- Round 16: submitted with k-boost fix, pending score
- Leaderboard: best weighted=179.0. Top teams: ~196 weighted.
- Gap to close: ~6-8 raw points. Need ~90 raw on later rounds to compete.

---

## Phase 4: Close the Gap to Top Teams

### Competitive Position
- R6 score: 78.5 (rank 28/186). R7 score: 60.36 (rank 83/199).
- Leaderboard = **best round score × round weight**. Weights compound 5%/round.
- R7 regression caused by harsh winter (7% survival) and observation sparsity.
- Phase 4 targets both issues with calibration and fewer buckets.

### Round 6 Error Analysis (where we actually lose points)
| Source | Share of total KL loss | What goes wrong |
|--------|----------------------|-----------------|
| **Plains** (code 11) | **55.7%** | Misjudge Empty/Settlement/Forest balance near settlements |
| **Forest** (code 4) | **30.1%** | Underestimate Port creation on coast, miss expansion |
| Settlement (code 1) | 3.6% | Per-cell KL high (0.14) but few cells |
| Port (code 2) | 0.7% | Extremely high per-cell KL (0.83!) but only ~5 cells |

### What we tried and learned across rounds:
- **Graduated forest adjacency (0/1/2/3+)**: Tiny improvement → reverted to binary in Phase 4
- **Forest adjacency on empty/ruin cells**: **Big win** for harsh winters (R3: 0.075→0.067)
- **4-level distance buckets**: **Consistently hurts** — fragments data, don't try again
- **Bayesian bucket smoothing (K=5)**: Small but consistent wins. K=20 too aggressive.

---

### 4a. Fix viewport position bug ✅ (committed before R8)
+425 cell-observations per coverage pass (+26%).

### 4b. Continuous distance interpolation ✅ (R8 submission)
Blends between adjacent distance brackets based on raw Manhattan distance.
Uses midpoints [1.0, 3.5, 7.0] for linear interpolation. Applied at prediction
time only — bucket training unchanged.

### 4c. Winter severity calibration ✅ (R8 submission)
`estimate_survival_rate()` counts how many initial settlement/port cells survived
in observations. Scales model's settlement/port predictions to match observed rate.
Clamped to [0.3, 3.0] to avoid wild swings. R8 saw 7.1% survival → correctly
scaled down from model's average.

### 4d. Port probability fix ✅ (R8 submission)
Coastal cells within d≤3 of settlements get minimum Port probability (5% if d≤1,
3% if d≤3). Deficit taken from dominant non-Port class.

### 4e. Simplified bucket keys ✅ (R8 submission)
Reduced from ~30 to ~20 buckets:
- Settlement: binary `has_adj_forest` (was graduated 0/1/2/3+)
- Port: `is_coastal` only (was `adj_forest_level`)
- Ruin: dropped `has_adj_forest`
- Plains, Empty, Forest: unchanged

### 4f. Settlement cluster density ✅ (committed)
Binary `is_clustered` (≥2 settlements within Manhattan d≤5) added to Settlement and Plains
bucket keys. Tested 3 variants: both (best), settlement-only, none.
- R7 improved 0.1468→0.1416 (biggest gain — clustered vs isolated settlements behave differently in harsh winters)
- R1-6 avg 0.0568→0.0576 (slight regression — more buckets = less data per bucket)
- R1-7 avg improved overall due to R7 gain

### 4g. Settlement stats extraction ✅ (committed, pending live validation)
`extract_settlement_stats()` parses food/population/wealth from simulate query responses.
- Level 1: avg_food modulates winter calibration scale (±20%, clamped)
- Level 2 (per-cell food z-score) and Level 3 (expansion signal) not yet implemented
- Schema discovery blocked by rate limit — wired but safe no-op until live data confirms fields
- Cannot backtest (GT has no settlement stats)

### 4h. Forward model ✅ (implemented but DISABLED in production)
Rate estimation functions: expansion, port_formation, forest_reclamation, ruin.
Physics-based forward probabilities with context-dependent blending weights.

**Result: consistently hurts in backtesting.** Even at very low weights (3-10%), the
parametric formulas can't match the data-driven bucket model. Reasons:
- Bucket model already captures actual transition dynamics from observations
- Physics formulas use simplified exponential/linear approximations
- The bucket model has access to the same spatial features the forward model uses
- Forward model adds noise rather than correcting errors

**Kept for future use** — rate estimation functions may be useful for settlement stats
integration or as diagnostic tools.

### 4i. Deploy to Cloud Run (DO WHEN MODEL IS GOOD)
- [ ] Deploy Dockerfile to Cloud Run
- [ ] Register endpoint at app.ainm.no
- [ ] Automated round handling via /solve endpoint

---

### R8 submission summary
All 4 priority items implemented and submitted:
- 4a viewport fix ✅, 4b distance interpolation ✅, 4c winter calibration ✅, 4d port fix ✅, 4e bucket simplification ✅
- R8 round had 7.1% settlement survival (very harsh winter)
- Backtest: R1-6 avg 0.0568 (was 0.0594), R7 0.1468 (was 0.1506)

### Priority for Round 9+ (remaining items)
| # | Change | Status | Notes |
|---|--------|--------|-------|
| 1 | **Settlement cluster features** (4f) | ✅ Done | +3.5% on R7, slight regression R1-6 |
| 2 | **Parse settlement stats** (4g) | ✅ Wired, needs live validation | Food modulation of winter calibration |
| 3 | **Lightweight forward model** (4h) | ❌ Disabled | Consistently hurts in backtest |
| 4 | **Deploy to Cloud Run** (4i) | Not started | Automation |

### Overnight iteration findings (2026-03-20)

**Attempted and failed:**
- **Stronger forest entropy injection** ❌: Increased shrink max 0.15→0.22, multipliers up. R2 regressed +24.9% (0.0321→0.0400). The blunt shrink over-corrects on moderate rounds where forest retention is legitimately high. Needs per-round conditioning, not global strength.
- **Forest smoothing K reduction (4→2)** ➖: Zero effect in backtest. With 5 seeds of GT, each bucket has hundreds of obs so K barely matters. Only relevant in production with 50 queries.

**Current error profile (avg KL 0.0497):**
- Plains: ~60% of loss, wkl=0.048 avg — biggest target but hard to improve without regressing
- Forest: ~33% of loss, wkl=0.061 avg — worst cells are Forest near settlements (pred 89% vs GT 73%)
- R7 is the outlier (KL 0.124) — harsh winter. R3 also tough (KL 0.056, near-total collapse)
- Sp+Forward consistently worse than pure Spatial

**Attempted and improved:**
- **Widen expansion modulation d≤6→d≤8** ✅: Gradual decay d=5-8 instead of d=5-6. Overall KL 0.0497→0.0491 (-1.2%). R7 improved 0.1243→0.1218, R5 0.0542→0.0526. No regressions.
- **Distance-based temperature scaling** ✅: Replaced Step 1.8 prior-blending with temperature scaling (d≤2: T=1.10 spread, d=3-4: T=1.03, d≥5: T=0.92 sharpen). Overall KL 0.0491→0.0457 (-6.9%). R3 -19%, R7 -11%, R5 -10.6%. Key insight: model had bidirectional calibration failure — over-confident near settlements, under-confident far away. Temperature scaling fixes both directions simultaneously.

**Attempted and failed/neutral (2026-03-20 evening):**
- **Per-terrain temperature** ➖: Forest d≤2 T=1.04, d≥5 T=0.95, Plains unchanged. Overall neutral (0.0457→0.0457). R2 improved slightly but R3/R8 regressed. Not worth the complexity.
- **Expansion-modulated forest injection** ❌: Boost forest entropy injection proportional to expansion_rate. R2 regressed +29.6% because expansion_rate measures settlement growth into Plains, NOT forest clearing. High expansion ≠ high forest clearing.
- **Spatial smoothing (MRF-style)** ❌: 8-connected neighbor averaging (alpha=0.08) near settlements. R4 regressed +10.4% — blurs predictions across terrain boundaries, adding noise to already-accurate moderate rounds.
- **Temperature parameter tuning (1.12/1.05/0.94)** ➖: More spreading near, less sharpening far. Overall neutral (0.0457→0.0457). R7 improved 1.3% but R2/R4/R8 worsened. The (1.10/1.03/0.92) values appear to be a local optimum.

**Key lesson**: The temperature scaling parameters are already well-tuned. Post-model adjustments have diminishing returns. The remaining error is dominated by within-bucket variance (irreducible without better features).

### Overnight iteration findings (2026-03-21)

- **Adjacent settlement count for Plains** ✅: Added adj_sett_level (0/1/2+) to Plains bucket key. KL 0.0435→0.0428 (-1.6%). R7 -2.1%, R3 -6.9%. Cells adjacent to 2+ settlements have much higher expansion probability — this feature directly captures expansion pressure.
- **Cluster density for Forest** ✅: Added is_clustered to Forest bucket key. KL 0.0428→0.0415 (-3.0%). All rounds improved, best R8 -4.0%, R9 -2.4%, R7 -1.9%. Forest near clustered settlements gets cleared more due to higher food demand.
- **Cluster density for Ruin** ➖: Added is_clustered to Ruin bucket key. Zero effect — Ruin cells are too few (~200 per map) to benefit from additional bucket features with 5 seeds of GT data.
- **Plains K increase (3→5)** ➖: Zero effect — with 5 seeds of GT data, buckets have hundreds of obs so K barely matters (same as forest K dead end).
- **Prob floor increase (0.003→0.005)** ❌: Regressed +7.8% — mass stolen from correct predictions outweighs safety net for rare events.
- **Prob floor decrease (0.003→0.002)** ✅: KL 0.0476→0.0459 (-3.6%). Uniform improvement across all 12 rounds. Lower floor preserves more mass for dominant class.
- **Prob floor decrease (0.002→0.001)** ✅: KL 0.0459→0.0446 (-2.8%). All rounds improved again. Monotonic trend. May try 0.0005 next.

**Promising directions not yet tried:**
- Plains bucket refinement: split by distance + cluster density interaction
- Ruin-to-forest transition: currently under-predicted, especially near forests in harsh winters
- Ensemble approach: run predictions with multiple parameter sets and average
- Non-linear feature interactions: multiplicative features in bucket key (e.g., coastal AND clustered AND near_forest)

### Saturday session findings (2026-03-21)

**Investigated and dead-ended:**
- **Terrain-aware A* distance** ❌: Tested all 12 rounds — 0 cells have different terrain distance vs Manhattan distance. Mountains on competition maps are small clusters (2-5 cells) that can always be walked around. The map generator never creates complete barriers. Do NOT retry.

**Key discovery: backtest→production gap is 53%:**
- Simulated production (50 queries, sampled from GT) gives KL ~0.154 for R7
- Backtest (GT data) gives KL 0.101 for R7
- The observation noise is where most points are lost, not the model itself
- Per-cell blending k values (k=3/8) already well-tuned (tested in simulation)

**Error analysis (worst cells on R7):**
- **Port under-prediction** is the #1 cell-level error: GT shows 20-45% port for coastal forest cells near settlements, model predicts 1-2%
- **Settlement expansion under-prediction**: Plains near settlements have GT Sett=24-61%, model predicts 3-13%
- **Forest over-prediction**: Forest near settlements has GT Forest=13-41%, model predicts 47-90%

**Implemented and improved:**
- **Rate-adaptive port calibration** ✅: Uses observed `port_formation_rate` to scale port minimums (was fixed 5%/3%). Extends to d≤5. R8 improved -7.9% (survival calibration also now tested in backtest).
- **Prob floor 0.001 → 0.0005** ✅: KL 0.0442 → 0.0442... wait, the improvement was -0.7% from previous baseline. All rounds improved, zero regressions. Monotonic trend continues (0.0002 and 0.0001 also improve in backtest but risky in production).
- **Focused query strategy** ✅: Half queries for coverage, half for repeating high-settlement tiles. -2.1% in simulated production. Gives 2-3x observations of high-entropy cells.
- **Monte Carlo forward simulator** ✅: Simplified Norse world sim (growth, expansion, ports, winter, environment). 80 runs × 50 years. Blended at 5% weight only when survival_rate > 0.50. R12 improved -7.4%. Overall -1.7%. Zero regressions.

**MC simulator details:**
- Helps dramatically on R7 (-14% at 10% weight in isolation) and R12 (-7.4%)
- Hurts on R1/R2/R6 when applied with survival > 0.25 threshold (mechanics are uncalibrated for moderate survival)
- Current threshold of survival > 0.50 is safe — only catches R12-type rounds
- Calibration challenge: per-year rates are hard to derive from 50-year outcome rates

**Current backtest: 0.0435 avg KL** (was 0.0446 at start of session, -2.5% total)

**Remaining promising directions:**
1. Better MC calibration → lower threshold to 0.40 to catch R7
2. Ensemble of 2-3 model configurations
3. Participation in later rounds (weight compounds 5%/round)

### Critical discovery: oracle backtest is misleading (2026-03-21 afternoon)

**Built simulated-production backtest** (`--simulate-production` flag in test_backtest.py) that samples discrete terrain from GT, limits to 50 queries with actual viewport strategy, and runs full production pipeline.

**Key finding: oracle backtest has rho=0.750 rank correlation with production scores, simulated-production has rho=0.964.** The oracle was systematically misleading us:
- It trains on full GT probability vectors (production only sees discrete samples from 50 queries)
- It covers 100% of cells (production covers ~70%)
- It skips per-cell blending (production uses it)
- It evaluates on the same data it trained from (no train/test split)

**The oracle backtest was optimizing in the wrong direction.** Two changes improved oracle but hurt production:

| Change | Oracle Impact | SimProd Impact | Root Cause |
|--------|--------------|----------------|------------|
| Focused query strategy (half coverage, half repeats) | Helped per-cell blending | **-5 to -23% worse** every round | Less spatial bucket coverage |
| Extra bucket features (adj_sett Plains, cluster Forest) | -1.6% to -3.0% better | **-5 to -9% worse** every round | More buckets = less data per bucket with 50 queries |

**R13 scored 73.2 (rank 126/186)** — oracle predicted it would be our 2nd best round (KL=0.024), but simulated-production correctly ranked it 5th (KL=0.107).

**Fixes applied:**
1. Reverted to full-coverage query strategy (removed focused/repeat logic)
2. Removed adj_sett_level from Plains bucket key
3. Removed is_clustered from Forest bucket key

**Validation (simulated-production, 13 rounds, 5 runs each):**
- SimProd avg KL: 0.1070 → 0.1027 (**-4.0%**, every round improved)
- Oracle avg KL: 0.0420 → 0.0439 (**+4.7% regression** — confirming oracle was misleading)
- Best improvements: R5 +7.0%, R10 +6.7%, R12 +6.2%, R7 +5.4%

**Lesson: ALL future model changes must be validated with `--simulate-production`, not oracle backtest.** The oracle is useful as a ceiling (what's possible with perfect info) but cannot be used for A/B testing changes.

### Production scores (updated 2026-03-21)
| Round | Score | Rank | SimProd KL | Oracle KL |
|-------|-------|------|------------|-----------|
| R5 | 13.1 | 130/144 | 0.135 | 0.043 |
| R6 | 78.5 | 28/186 | 0.085 | 0.037 |
| R7 | 60.4 | 83/199 | 0.154 | 0.101 |
| R8 | 82.4 | 55/214 | 0.062 | 0.016 |
| R9 | 8.5 | 205/221 | 0.121 | 0.023 |
| R10 | 82.0 | 60/238 | 0.073 | 0.033 |
| R11 | 79.7 | 61/171 | 0.074 | 0.029 |
| R12 | 59.4 | 38/146 | 0.165 | 0.112 |
| R13 | 73.2 | 126/186 | 0.104 | 0.024 |
| R14 | 74.1 | 71/244 | 0.082 | 0.047 |
| R15 | 86.1 | 97/262 | 0.050 | 0.022 |
| R16 | pending | — | — | — |

### R14 analysis and expansion modulation fix (2026-03-21 afternoon)

**R14 scored 74.06 (rank 71/244)** — degraded by accidental resubmission with only 5 observations (rate-limited). Estimated ~79 with proper data. Still our best weighted at 146.6 (R14 weight=1.98).

**R14 error analysis revealed root cause of Settlement over-prediction:**
- Settlement over-predicted by +11% on Plains (pred 39% vs GT 28%)
- This was 63% of total KL loss — the dominant error across ALL rounds
- Root cause: **Step 1.75 expansion modulation was double-counting** the expansion signal already captured by the spatial bucket model
- The spatial model learns P(Settlement | Plains, features) from observations
- Step 1.75 then separately estimates expansion_rate from the SAME observations and scales Settlement predictions multiplicatively → applying the signal twice
- On a typical round: spatial model predicts 25% Settlement, expansion modulation scales by 1.4x → 35%, but GT is 28%

**Fix: dampened expansion modulation**
- Changed from full override (`scale = expansion_rate / model_avg`) to 30% dampened correction (`scale = 1.0 + 0.3 * (raw_scale - 1.0)`)
- Tightened clamp from [0.3, 3.5] to [0.7, 1.5]
- Result: **SimProd KL 0.1027 → 0.0612 (-40.4%)**, every round improved

**Port fixes:**
- Increased per-cell blending K from 8→15 (ports have too few observations for aggressive blending)
- Reduced port calibration multipliers (1.5→1.0, 0.8→0.5) and caps (0.40→0.25, 0.25→0.15)

**MC simulator disabled:** Hurts +1.1% in simulated production (+3.7% on R12). Uncalibrated per-year rates add noise.

**Query bug fixed:** observe_seed now uses ALL allocated queries (coverage + repeats of top tiles) with rate-limit retry on 429 errors. Never waste queries.

**R15 submitted** with all fixes. Survival=34.6%, 60 spatial buckets, 50/50 queries used.

### R15 scored 86.1 (rank 97/262) — best raw score ever (2026-03-21)

**R15 analysis revealed per-cell blending as dominant error source:**
- Ruin over-predicted by 20pp on Plains near settlements (pred 21% vs GT 0.5%)
- Settlement over-predicted by 30pp on Forest near settlements (pred 49% vs GT 18%)
- Root cause: with 50 queries, most cells get 1-2 observations. Per-cell blending with k=3 gives a single outlier 25% weight → wildly inflated rare-class predictions.
- Survival/expansion rate estimates too noisy from 50 queries (estimated 33% survival vs 9.4% GT) — rate-dependent fixes don't trigger.

**Fix: sparse observation k-boost**
- For Plains/Forest/Empty cells with ≤2 observations: k *= 3.0 (k=3→9)
- Trusts the bucket model more when per-cell data is unreliable
- SimProd backtest (5 runs, 15 rounds): **-10.9% avg KL, 15/15 rounds improved, zero regressions**

**R16 submitted** with k-boost fix. Survival=30.8%, 58 spatial buckets, 50/50 queries used.

**Further iteration (2026-03-21 evening):**
- Graduated k-boost (k*4/n continuous) ➖: Marginal (<0.5%) improvement, within noise. Current k*3 binary threshold is already near-optimal.
- Skip-1-obs blending ➖: Marginal on most rounds, regressed on R14. Single obs still provides some signal via blending.
- Viewport size tuning: Analysis showed 15×15 (max) is optimal — smaller viewports need more tiles than 10-query budget allows.
- **Conclusion**: Per-cell blending is now well-tuned. Remaining oracle→sim-prod gap (26%) comes from spatial bucket coverage limits with 50 queries.

### Deep research sprint (2026-03-21 evening)

**Gap analysis** identified 3 mechanisms driving the 26% oracle→sim-prod gap:
1. Discrete sampling noise in bucket distributions (63.3%) — structural, hard to fix
2. **Expansion rate estimator broken** (36.7%) — estimate_expansion_rate() divided by obs_count not cell_count, hit 0.50 clamp on every round (true rates: 0.13-0.28)
3. Per-cell blending noise (7.8%) — partially fixed by k-boost

**Expansion rate fix**: Changed `new_settlements / obs_count / avg_initial` to `new_settlements / observed_non_settlement`. SimProd -6.1% avg KL. 13/15 rounds improved, R7/R12 regressed (extreme rounds where accidental over-boost helped).

**Tested and rejected:**
- Ensemble predictions (3 k-configs averaged) ➖: Zero effect — configs too similar, bucket model dominates
- Adaptive two-phase queries ❌: 60/40 split reduced coverage, KL regressed -19% on R15
- Historical round prior ❌: Cross-round averaging adds noise since hidden params differ per round
- Neural network predictor: NO-GO — only 16 independent rounds, bucket model already captures what NN would learn, hidden param variation makes generalization unreliable

**Combined improvements this session**: baseline 0.0603 → k-boost 0.0537 (-10.9%) → expansion fix 0.0504 (-6.1%) = **total -16.4% improvement**.

### ML Model (2026-03-21 night) — CURRENT PRODUCTION MODEL

**Replaced bucket model with PyTorch MLP trained on cross-round GT data.**

The bucket model's fundamental limitation was within-bucket variance — it couldn't learn
feature interactions (e.g., coastal AND near settlement AND near forest). An MLP trained
on 985k GT cells from 17 rounds captures these interactions.

**Architecture**: Input(18) → Linear(128) → ReLU → Dropout(0.1) → Linear(64) → ReLU → Dropout(0.1) → Linear(32) → ReLU → Linear(6) → Softmax. KL divergence loss, Adam optimizer, cosine annealing, early stopping.

**Key innovation**: Noisy rate augmentation. Instead of using perfect GT rates during training,
we simulate production noise by sampling discrete observations from GT and estimating rates
from those (matching the 50-query viewport strategy). The model learns to be robust to 2-4x rate estimation noise.

**Results (simulated-production, 3 runs, 17 rounds)**:
| Metric | Bucket Model | ML Model | Improvement |
|--------|-------------|----------|-------------|
| Avg KL | 0.0494 | **0.0341** | **-31%** |
| R3 (harsh) | 0.0524 | 0.0198 | -62% |
| R7 (harsh) | 0.1028 | 0.0746 | -27% |
| R10 | 0.0466 | 0.0192 | -59% |
| R12 (harsh) | 0.1297 | 0.0856 | -34% |
| R15 | 0.0334 | 0.0198 | -41% |

Zero regressions across all 17 rounds.

**R18 submitted** with ML model. First production test of the new approach.

**Files**:
- `ml_predictor.py`: Feature extraction (18 features) + numpy forward pass
- `train_model.py`: GT data fetch, noisy augmentation, PyTorch training, LOOCV
- `model_weights.npz`: Trained weights (53KB, committed)
- `predictor.py`: Added `build_prediction_ml()` — ML base + per-cell blending + floor
- `main.py`: Auto-loads ML weights at startup, falls back to bucket model

**Retraining after new rounds**:
```bash
rm training_data.npz && python3 train_model.py --augmentations 10 --output model_weights.npz
```

**Improvement directions**:
- More features: adj_mountain, distance_to_coast, settlement_count_in_radius
- Architecture: wider layers, residual connections
- Ensemble: alpha-blend ML + bucket predictions
- Each new round adds ~5800 cells × 10 augmentations of training data

---

## Simulation Phase Summary (for modeling reference)

Each of 50 years runs these phases in order:
1. **Growth** — food from adjacent terrain, population growth, port development, expansion
2. **Conflict** — raids (longships extend range), desperate raids if low food, allegiance changes
3. **Trade** — ports trade if not at war, generates wealth+food, tech diffusion
4. **Winter** — severity varies (hidden param!), food loss, collapse → Ruin
5. **Environment** — forest reclaims ruins, settlements reclaim/rebuild nearby ruins, unreclaimed ruins → forest/plains

Key dynamics:
- Settlement survival = f(food from forests, winter severity, raid exposure)
- Expansion = f(prosperity, available nearby land)
- Port formation = f(coastal position, settlement prosperity)
- Ruin fate = f(nearby settlement strength, time) → either reclaimed or overgrown

---

## How to Iterate

### Workflow for each improvement:
1. Make the code change in a worktree
2. Run fast gate: `pytest test_predictor_unit.py test_predictor_integration.py -x --tb=short`
3. Run backtest gate: `python3 test_backtest.py --output results.json --baseline baseline.json`
4. Keep only if no regression detected (exit code 0)
5. If improved: `cp results.json baseline.json` to update baseline
6. Commit and merge

### Overnight self-improvement loop
The test suite is designed for automated iteration. The loop:
```bash
while true; do
  # 1. Apply next hypothesis (parameter tune, feature experiment)
  # 2. Fast offline gate (< 1s, no API):
  pytest test_predictor_unit.py test_predictor_integration.py -x --tb=short
  #    → FAIL? Revert, try next hypothesis
  # 3. Backtest regression gate (~30s, requires API):
  python3 test_backtest.py --output results.json --baseline baseline.json --threshold 0.10
  #    → EXIT 1 (regression)? Revert, try next hypothesis
  # 4. If improved: cp results.json baseline.json
  # 5. If active round: python3 test_local.py --submit
  # 6. Log results, continue
done
```

**Backtest JSON output** (written by `--output`) contains everything needed to guide the loop:
- `overall.avg_weighted_kl` — single number to compare
- `per_round[].per_terrain_kl` — which terrain types improved/regressed (Plains is 55% of loss)
- `per_round[].worst_cells` — top 10 worst cells with bucket_key, GT vs pred distributions
- `per_round[].model_variants` — spatial vs spatial+forward comparison
- `regression` — populated when `--baseline` is used, null if no regression

**Exit codes**: 0 = pass, 1 = regression detected, 2 = error

**Generating initial baseline**:
```bash
python3 test_backtest.py --output baseline.json
```

### When a new round starts:
```bash
python3 test_local.py --list-rounds          # find the active round
python3 test_local.py --round ROUND_ID       # quick test (uses 4 queries)
python3 test_local.py --submit               # full pipeline: 50 queries + submit
```

### After a round completes:
```bash
python3 test_local.py --my-rounds            # check our score and rank
python3 test_backtest.py --round ROUND_ID --output results.json  # detailed analysis
python3 test_backtest.py --output baseline.json                  # regenerate baseline with new round
python3 test_local.py --leaderboard          # check standings
```

### To debug a specific round:
```python
import api_client, numpy as np
# Get ground truth
analysis = api_client.get_analysis(round_id, seed_index)
gt = np.array(analysis['ground_truth'])
pred = np.array(analysis['prediction'])  # our submitted prediction

# Compare
kl = np.sum(gt * np.log((gt + 1e-10) / (pred + 1e-10)), axis=2)
# Look at worst cells
worst = np.unravel_index(kl.argmax(), kl.shape)
print(f"Worst cell: {worst}, KL={kl[worst]:.4f}")
print(f"  GT: {gt[worst]}")
print(f"  Pred: {pred[worst]}")

# Check our predictions with confidence
preds = api_client.get_my_predictions(round_id)
```
