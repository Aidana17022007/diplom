# Exact data restoration and cross-year transfer

These commands run in the Python environment of the full CardioResearch archive,
not in the hosted Worker. They do not replace model artifacts or frozen reports.
Public source tables remain local and must not be copied into the Site repository.

## One-command verification

From the extracted full project, after installing its recorded Python requirements:

```powershell
python deployment/cardio-site/scripts/verify-research.py --project-root . --source-dir data/source-cache --download
```

The command downloads the public CDC BRFSS2023 ZIP if missing (about 93 MB), checks
its exact original SHA-256, runs the existing deterministic cleaner and split, and
reconstructs Cleveland from the original archived center-audit CSV. It refuses a
different BRFSS source version. It then runs the original Python tests without
changing their assertions or skipping missing-data tests. Only the sample PDF's
output path is redirected from the frozen report directory to
`data/processed/verification/`. Recovery fingerprints and JUnit results are saved
there. No original model is trained, calibrated, selected or overwritten.

For restoration without tests, use `prepare-research-data.py` with the same
arguments. Its `--datasets uci` option restores only the small Cleveland table
without a download. Existing processed tables are compared to the reconstruction
and are never silently overwritten.

The restored BRFSS data have 428,738 retained rows: 342,990 train and 85,748 test.
The exact original test row IDs, targets and weights are checked. Applying the
frozen model to every restored test row reproduced the saved probabilities with
maximum absolute difference 9.98e-17. The UCI table has 303 Cleveland rows and
139 positives; its row IDs and targets match the saved OOF table.

## BRFSS2024 transfer audit

Sources:

- [CDC 2024 data and documentation](https://www.cdc.gov/brfss/annual_data/annual_2024.html)
- [Official XPT archive](https://www.cdc.gov/brfss/annual_data/2024/files/LLCP2024XPT.zip)
- [Official codebook archive](https://www.cdc.gov/brfss/annual_data/2024/zip/codebook24_llcp-v2-508.zip)
- [Variable layout](https://www.cdc.gov/brfss/annual_data/2024/llcp_varlayout_24_onecolumn.html)

Download the two archives into a local source cache, then run:

```powershell
python deployment/cardio-site/scripts/evaluate-temporal.py --project-root . --source data/source-cache/LLCP2024XPT.zip --codebook data/source-cache/codebook24_llcp-v2-508.zip --output reports/temporal.json
```

The script pins both source hashes and audits the XPT and codebook. The nine
available model variables retain their original meanings/codes, including BMI
scaled by 100 and day code 88 meaning zero days. The target remains an affirmative
answer to myocardial infarction OR coronary heart disease, with a negative target
only when both answers explicitly say no; it is checked against `_MICHD`.

`BPHIGH6` (hypertension) and `TOLDHI3` (cholesterol history) are absent in 2024.
They become missing values and pass through the frozen categorical missing-value
encoding, not a healthy-category replacement. Three cohorts are reported:

1. Original BRFSS2023 held-out test with its original predictors.
2. The identical test observations with those two predictors hidden.
3. BRFSS2024 with the two unavailable predictors missing for all observations.

All use the original calibrated Logistic Regression artifact and its unchanged
threshold. The 2023 masking control is a paired sensitivity experiment, not a new
independent validation cohort. The 2024 result combines year, population and
predictor-availability changes, so it is not a clean estimate of temporal drift.
Neither dataset follows the same individuals over time or establishes future-event
risk. This is exploratory transportability work, not clinical/Kazakhstan validation.

Primary metrics are unweighted; supplementary survey-weighted point estimates are
retained in JSON. These weights do not supply survey-design confidence intervals.
Changing prevalence also affects Average Precision. No 2024 result is used to
refit, calibrate, select a model or tune a threshold. The public JSON contains
aggregate counts, metrics, calibration bins, missingness and provenance only.
