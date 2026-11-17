# Bounded local experiment laboratory

The laboratory is a **new descriptive experiment**, separate from the original
BRFSS benchmark, BRFSS held-out test and UCI nested cross-validation. It does not
overwrite or deploy any fitted model. The default generated report contains
four measured configurations: Logistic Regression and Random Forest for UCI and
BRFSS, with seed `20261109`.

## Data and evaluation

- UCI: all 303 Cleveland observations, with the existing 13-feature definition
  and target `severity > 0`.
- BRFSS: a deterministic stratified sample of 6,000 rows from the **original
  training pool only**. The original 85,748-row held-out test is not used.
- Three stratified outer folds; one fixed configuration per run; threshold 0.5;
  unweighted evaluation. Both classifiers use `class_weight='balanced'`.
- Numeric median imputation and scaling are fitted inside each training subset.
  Categorical unknown-value imputation and one-hot encoding use the existing
  documented fixed category lists. Evaluation rows never fit preprocessing.
- Logistic Regression: C chosen from 0.1, 1, 10; at most 1,500 iterations.
- Random Forest: 100 trees, depth chosen from 3, 5, 8, minimum leaf size 3,
  at most two workers. This is a bounded research configuration, not the
  originally selected deployed artifact.

## Learning curves

Training fractions 20%, 40%, 60%, 80%, 100% use deterministic nested subsets of
each outer training fold, stratified by class. The same held-out fold is used
for all five fractions. Every point reports actual training counts, training
and validation metric means, sample SD, and measured fitting time. The baseline
is exactly the validation summary at 100% training fraction.

## Stress tests

Each full outer-fold model is evaluated on its own held-out fold. It is not
refitted on perturbed data. There are three deterministic perturbation repeats
per fold, except the deterministic single-feature removal.

- Missing values: independently mask 0%, 5%, 10%, 20% of feature cells. These are
  **additional MCAR probabilities**, not guaranteed final missingness rates.
  Existing missing values remain missing; actual total missingness is recorded.
  Reusing uniform draws across levels yields nested masks for paired comparison.
- Numeric noise: Gaussian standard deviation equal to 0%, 5%, 10%, 20% of each
  numeric feature's outer-training standard deviation. Values are clipped to
  documented UI bounds; integer measurements are rounded. Categories and
  pre-existing missing values are unchanged.
- Feature removal: mask every value of one feature, retaining the others.
- Deltas are paired stressed-minus-original fold metrics. A negative AP delta
  and a positive Brier delta indicate worse scores. No monotonic degradation is
  assumed: measured values are retained, even when a perturbation improves one
  metric in this sample.

The same observations appear in multiple perturbation evaluations. `unique_n`
counts unique source observations; `evaluations` counts fold/repeat evaluations,
not independent new patients. SD is descriptive across these dependent
evaluations, **not a confidence interval**. Missing precision remains null when
there are no positive predictions, with the valid evaluation count retained.

## Reproduce

From this repository, using the original project's Python environment:

```powershell
python scripts/build-experiment-lab.py --project C:\path\CardioResearch
```

The script reads restored `data/processed/uci.pkl` and `brfss.pkl` and writes
only `data/experiment-lab.json` by default. It never updates original model or
research files. It records hashes of the prepared dataset, selected row IDs,
fold indices and implementation, plus library versions. These hashes are
provenance, not public exports of respondent identifiers.

Meaningful tests live in `python/tests/test_experiment_lab.py`. Set `PYTHONPATH`
to the original Python project when running them from this repository. They
verify nested/disjoint folds, training-only preprocessing, stress semantics,
undefined metrics, original BRFSS split preservation, cancellation and local
API access controls. Test fixtures are explicitly synthetic and do not generate
the committed research report.

## Local service

Register `register_experiment_lab_routes(app, ROOT)` in the Python API. The
service permits one active job, cooperative cancellation between fit/scoring
steps, 12 in-memory jobs, and 24 persisted aggregate results. Page refresh can
recover the active job; completed aggregate results survive server restart.
Metadata/results are stored only under `reports/experiment_lab_runs`.

- `GET /api/experiment-lab`: measured reports and local capabilities.
- `POST /api/experiment-lab/runs`: allowlisted configuration, maximum 2 KiB JSON.
- `GET /api/experiment-lab/runs/{id}`: progress, state and completed result.
- `POST /api/experiment-lab/runs/{id}/cancel`: cooperative cancellation.

Execution requires both a loopback client and loopback Host. Writes require an
exact same-origin header and reject cross-site requests. The local application
continues to bind to loopback; no training endpoint is enabled on public
hosting. Hosted results are aggregate read-only reports.

These experiments measure algorithm behavior under the specified protocol.
Repeated tuning against them would require a fresh independent evaluation.
They establish neither clinical validity nor future-event prediction.
