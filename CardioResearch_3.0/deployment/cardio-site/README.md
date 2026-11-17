# CardioResearch hosted application

## Application 3.2

The comparison explorer now provides 13 metrics, a bilingual glossary, direction-aware deltas and CSV/SVG exports. UCI derived metrics are averaged from individual outer folds; undefined ratios remain unavailable. `/api/metrics-insights` serves saved cumulative gains/lift, missingness strata and frozen validation/test selection context. `/api/development-study` serves a new four-model, three-fold study on 36,000 rows of the original BRFSS fit pool only.

The highest study AP is 0.317151 versus LR 0.316295 (+0.086 percentage points), with a positive difference in only one of three folds. This does not establish an improvement. Production models and thresholds are unchanged. These public endpoints expose aggregates; exact observations remain excluded. Both UI builds and 85 Worker / 117 Python tests passed; browser QA of these new panels was unavailable. Existing Sites publication access remains unavailable.

## Application 3.1

The experiments hub now exposes saved SHAP, prevalence, calibration and missingness diagnostics through aggregate-only `/api/scientific-audit`. The overview adds saved Wilson intervals and calibration-bin tables. The artery atlas supports a resilient 2D fallback, PNG export and explicit return to 3D. The frozen predictors and thresholds are unchanged. Full local Python mode and this hosted UI share matching source files. Publication to the existing Sites account remains unavailable; the built bundle is ready locally.

## Diploma topic supplied by the student

- Қазақша: Жүрек-қан тамырлары ауруларын болжауға арналған машиналық оқыту модельдерін әзірлеу
- Русский: Разработка моделей машинного обучения для прогнозирования сердечно-сосудистых заболеваний
- English: Development of Machine Learning Models for Cardiovascular Disease Prediction

Canonical wording and scope are stored in `data/thesis-topic.json` and displayed at `#thesis`. Current predictions concern disease presence/history from BRFSS and UCI features, without a future-event time horizon. The core contribution is model development, comparison and evaluation; the artery visualization is supplementary. Release 2.5.1 records the supplied titles without changing models or metrics.

This directory is the deployable Cloudflare Worker edition of the real diploma application. Training remains in the Python project. The hosted API uses the exact fitted Logistic Regression and Random Forest parameters exported from those saved artifacts; it does not train models or substitute synthetic probabilities.

## Rebuild

Run `npm ci` and `npm --prefix client ci`, then `npm run build` and `npm test` in this directory. `npm run dev` serves the built Worker locally on port 8787. The build now type-checks and builds `client/`, refreshes generated assets in `public/`, and bundles the Worker. Use Node 24 for the Sites packaging workflow on Windows.

## Version 3.0: measured experiments and reproducibility

- `#experiments` brings together an eight-algorithm UCI disagreement matrix, paired error counts and aggregate vote patterns. At the common 0.5 threshold, the seven trained algorithms disagree on 94/303 observations and are unanimously wrong on 19/303. Dummy remains a visible reference; agreement is not confidence.
- Four measured learning/stress experiments compare Logistic Regression and Random Forest on UCI (303) and a stratified 6,000-row sample from the original BRFSS training pool. Five training fractions, three folds, additional missingness, numeric noise and feature removal are evaluated without fitting preprocessing on validation rows. These are separate descriptive experiments, not replacements for the original benchmark. See [the protocol](docs/EXPERIMENT_LAB.md).
- The full local Python application can run a new bounded experiment, show progress, cancel it between steps and retain aggregate results. Hosted mode displays completed results and explicitly disables training. Inputs to the runner are allowlisted configuration values, not uploaded health records.
- Frozen BRFSS 2023 Logistic Regression is evaluated on 452,464 labelled 2024 observations. Two original predictors are absent in 2024; a same-row masked-2023 control makes this incompatibility visible. Recall is 0.5073 on the original test, 0.3262 after masking, and 0.3171 on 2024. These observations do not isolate a causal year effect or constitute clinical validation. Source definitions, exclusions, weights and limitations are retained in `data/temporal.json`.
- The original processed UCI and BRFSS tables are restored from verified sources. All 85,748 saved BRFSS test predictions reproduce to floating-point tolerance. The full local ZIP includes the processed tables and recovery manifest; the hosted repository includes only aggregate reports and recovery code. See [reproduction instructions](docs/DATA_REPRODUCTION.md).
- The educational artery offers synchronized healthy/altered views, shared camera and section controls, responsive stacked panels and one PNG containing both views. It remains separate from the classifier.

Release verification is recorded in `verification-v3.0.json`. Original trained models, original reports and manuscript drafts are preserved; no future-event prediction horizon is introduced.

## Version 2.8: research dashboard, exports and chart performance

- The overview dashboard reads the existing aggregate evaluation report. BRFSS shows the unweighted held-out test of 85,748 observations; UCI shows averaged OOF predictions for 303 Cleveland observations. The latter is distinct from the mean of six outer CV scores and is not an independent evaluation of the final fitted artifact. AP, ROC-AUC, Recall, Precision, confusion counts, calibration and Brier retain these scopes; the class prevalence is a descriptive AP reference, not another trained model.
- Model comparison remembers the selected pair and table preferences in the current browser tab using `sessionStorage`, with an in-memory fallback. State is separated by dataset, experiment, weighting and result contents. This stores preferences for aggregate results, not submitted prediction forms. CSV and SVG exports identify the comparison context, models, available sample sizes and thresholds; CSV retains metric precision, available fold SD and the descriptive difference B minus A. Missing metadata remains unspecified. Fold SD is not a confidence interval, and a score difference does not establish statistical superiority.
- Charts share a lazy-loaded official Plotly Cartesian 3.7.0 distribution instead of the full distribution. Scatter, bar, pie, heatmap and error bars remain supported. A PNG action exports the rendered chart at double resolution; loading, retry and export-error states remain available.
- The educational artery can expand to fullscreen, with an expanded-view fallback where native fullscreen is unavailable. Its PNG export includes the current view, parameters and legend. Geometry, selected cross-section and camera controls remain independent of model predictions; the image is not a patient reconstruction or blood-flow simulation.
- No model retraining, threshold reselection, changed research scores or manuscript regeneration is part of this release. The new interface is checked separately from the local Python backend.

Local Python verification used a fresh Python 3.12.14 environment and the backend from `CardioResearch_2.7_project.zip`, whose model/API implementation is retained for 2.8. The complete archived suite produced **43 passed and 2 failed**: the two observed-row Python/JavaScript parity tests require optional `data/processed/brfss.pkl` and `data/processed/uci.pkl`, which are absent from that archive. The tests were not skipped, rewritten or supplied with substitute data. `pip check` passed, dependencies were recorded with `pip freeze`, and all 68 checked model/report file hashes remained unchanged. The sample PDF test output was redirected outside the frozen reports directory.

A separate local smoke run passed **43 API requests**: both saved models in RU/KZ matched direct Python predictions, four PDF responses had valid PDF signatures and embedded fonts, and batch validation/CSV, evaluation CSV/JSON, transfer aggregates and the literature endpoint succeeded. PDF visual layout was not rendered in this smoke run. These backend results do not constitute frontend, clinical or new training validation. Release-specific Node, build and browser evidence is recorded separately in `verification-v2.8.json`; no final frontend test count is inferred from the Python run.

## Version 2.7: research interface and model comparison

- Readable workspace navigation with browser Back/Forward, focus handling, mobile menu isolation and accessible command search.
- Model tables offer focused metric sets, sticky algorithm names, sorting and pairwise comparisons. Deltas are descriptive differences; model selection remains fixed by the original protocol.
- The BRFSS threshold laboratory includes the exact saved working threshold alongside 35 measured validation grid points. It compares confusion counts, threshold-dependent metrics, differences and counts per 1,000 observations, with CSV export. It never changes deployed thresholds or evaluates threshold choices on the test set.
- The artery supports selecting a slice on its longitudinal profile, highlighting layers and a top camera view. Its renderer sleeps when paused and unchanged, hidden or offscreen.
- Charts expose loading, error and retry states. Model artifacts and frozen research results are unchanged; no manuscript editing is part of this release.

Verification: 45 Node tests passed, including seven threshold cases and two model-comparison cases. TypeScript, Vite and Worker build passed. Browser checks covered desktop/mobile, RU/KZ, navigation/focus, pairwise metrics, exact threshold reset, small deltas and the 3D profile. See `verification-v2.7.json`. The legacy Python ML suite was not rerun.

## Version 2.6: diploma structure, movable cross-section and literature

- `#artery` now has a movable cross-section, marked by a cyan ring and translucent plane in the existing 3D scene. Its coordinate is dimensionless. The controls distinguish maximum narrowing at the center from the local diameter, remaining area and area loss at the selected position. A reference section without narrowing is shown alongside it. At 50% maximum narrowing the center retains 25% of its area, while the unchanged ends retain 100%. This remains educational geometry, independent of ML probabilities.
- `#thesis` connects the exact topic in three languages with a three-chapter plan: literature and problem definition; data and model development; experiments and the application. Each chapter links to existing evidence and identifies remaining author work. The plan does not certify completed manuscript chapters.
- `#library` contains 43 catalog entries. The user-supplied 2026 Atherosclerosis review has RU/KZ summaries, a clear **abstract verified** badge and a PubMed link. Bibliographic information and the abstract were checked; the publisher's full text was inaccessible (403). The record distinguishes its theoretical relevance from model validation and does not present the article as training data or a CardioResearch benchmark.
- The local Python application receives the matching library addition and updated UI in `CardioResearch_2.6_project.zip`. Original models, existing experimental reports and draft documents are retained.

Version 2.6 verification: 36 Node tests and 6 isolated Python tests for aggregate API/library behavior passed. TypeScript/Vite/Worker build and the frozen-prediction metrics reproduction check passed. Desktop browser checks confirmed the 3D center/end area values and the RU/KZ library record. Mobile QA at a 390 px viewport confirmed the slice controls, three chapters and sequential topic titles with no horizontal page overflow; see `verification-v2.6.json` for the current scope. The full legacy Python training suite was not rerun, and existing manuscript files remain drafts.

## Version 2.5: diagnostic evaluation and cross-center transfer

`#evaluation` adds 19 metrics from frozen predictions, imbalance-aware interpretation, confusion counts, conditional Wilson intervals, calibration bin counts and probability distributions. JSON exports retain formulas and source hashes; CSV exports include context and intervals. The original UCI benchmark CSV now also retains fold SD.

A new exploratory experiment applies the fixed UCI artifact separately to 617 records from Hungary, Switzerland and VA. Missingness, zero-valued measurements and differences in class prevalence are reported alongside scores. No model or threshold was refitted. This is not clinical validation or an improvement claim. See [methods and reproduction](docs/EVALUATION.md).

Verification: 29 Node tests, 14 Python metric tests and 3 isolated FastAPI aggregate-route tests passed; the frontend type-checks and builds. Browser QA covered RU/KZ, calibration, histogram normalization, keyboard tabs, center selection and a 390 px mobile viewport. Earlier full Python ML tests were not rerun. The package script overlays the matching aggregate routes into the original Python application and preserves original models/reports/draft documents.

## Educational 3D and thesis readiness

- `#artery`: a lazily loaded Three.js artery with orbit controls, keyboard rotation, zoom buttons, a cutaway, paused-by-default illustrative particles, camera presets, and a 0–80% diameter-narrowing slider. An SVG cross-section stays available if WebGL cannot start. Radius and area calculations are independent of patient inputs and ML predictions; a 50% diameter reduction leaves 25% of the original circular area. This is simplified educational geometry, not a patient reconstruction or blood-flow simulation. Medical background: https://www.nhlbi.nih.gov/health/atherosclerosis.
- `#thesis`: thesis readiness, source-backed technical evidence, links to research sections, and a downloadable personal checklist. Old `#battle` bookmarks open this page. Existing thesis PDFs remain drafts. Official forms, signatures, manuscript review and department approval are pending.
- Both sections support Russian and Kazakh, are available to guests, and render independently of research API availability. Existing server authorization and model artifacts are unchanged.
- The automated suite includes geometry invariants alongside the existing authentication, prediction, scenarios, CSV and PDF checks.

## Remaining thesis-manuscript work

The archived `output/DRAFT_STATUS.txt` and `reports/university_pack_verification.json` identify the manuscript as a draft. The 100-page allocation is a plan, not a finished manuscript. This application update does not regenerate or certify those documents.

- The original `scripts/build_documents.py` still describes local-only operation, Russian-only UI and an older 14-test run. Update those passages against the actual web architecture, RU/KZ interface, scenarios and educational 3D. Keep historical Python and Worker test counts separate from a new run.
- Its original font, margins and page-number placement differ from the saved ENU requirements extract. Final layout needs the department's current instructions and visual review.
- The older `scripts/build_university_pack.py` statement about absent UCI intervals needs reconciliation with the conditional fixed-OOF bootstrap results in `reports/reliability.json`. These intervals do not measure uncertainty of the complete training procedure.
- Official department details, approved assignment, authentic declaration, Platonus report, signatures and final approval require the student's and university's confirmation. The source regulation PDF is not included in the archive; the stored JSON is an extract, not a fresh verification of university policy.

The original project contains `scripts/export_web_models.py` and `scripts/export_site_payload.py` to refresh model artifacts and aggregate research results. After refreshing, rerun the model parity tests before publication. The read-only experiment journal contains actual exported training snapshots; a new website deployment is not a new training run.

## Verification and scope

Version 2.2 adds an owner-only one-feature scenario API (`POST /api/scenarios`, at most nine distinct values and 32 KiB), fixed public examples (`GET /api/scenario-demo/{dataset}`), and an allowlisted aggregate reproducibility download (`GET /api/reproducibility/{dataset}`). Scenarios call the same fitted model and report probability differences, not causal effects or future clinical risk. The matching Python API is tested against the Worker outputs.

The frontend includes a scenario chart and table, up to four comparisons kept only while that page is mounted, an explicit owner CSV export, a searchable feature atlas, a metric glossary, defense rehearsal cards, an arithmetic BMI helper, quick section navigation, and model-table search/sorting. Rehearsal progress is a personal practice indicator, not evidence that scientific checks have passed. These additions do not retrain or reselect the deployed models.

- 1,063 BRFSS and 509 UCI cases were compared with the original Python artifacts, including missing values and forest split-boundary probes. Maximum observed probability difference was 2.22e-16.
- Shapley calculations use the same 48 orders and 30 background observations as the original application and explain raw probability before additional calibration.
- API tests cover actual prediction, validation, bounded CSV parsing, safe exports, PDF, unavailable routes and private file exclusion.
- Training environment metadata describes the original Python experiment. Hosted execution is JavaScript, not Python. Timing in research tables still describes the original experiment.

## Data boundaries

Only `public/` assets are exposed as files. Model parameters, SHAP backgrounds and report objects are bundled in server code. There is no model/background download endpoint. Aggregate report endpoints are explicitly enumerated; raw source archives, row identifiers, test predictions, student profile, full training tables and local SQLite files are excluded from this deployment.

The server temporarily receives submitted form values to calculate a result. The application does not persist those values, log request bodies or send them to an analytics service. Prediction, PDF and CSV responses use `Cache-Control: no-store`. CSV is limited to 1 MiB and 1,000 data rows; JSON is limited to 32 KiB.

The model bundle includes 30 predictor rows from each public source for Shapley calculations. Their original-source membership was checked; this is not a claim of formally proven anonymity. The owner explicitly authorized transferring this server-side bundle to the hosting provider.

## Public demo and owner access

The owner requested a publicly accessible demo without ChatGPT sign-in. Guests can read aggregate research and obtain two fixed, clearly marked synthetic example predictions. Arbitrary form predictions, PDF reports and CSV upload/processing require the owner session on the server; disabling interface controls is not the authorization boundary. The demo endpoint ignores additional input and uses only its predefined rows.

Configure `CARDIO_AUTH_USERNAME`, `CARDIO_AUTH_PASSWORD_HASH` and `CARDIO_SESSION_SECRET` as secret hosting environment variables. Never commit their values. Password hashes use `pbkdf2-sha256$100000$<base64url salt>$<base64url digest>` with PBKDF2-HMAC-SHA256, a random 16-byte salt and a 32-byte digest. The session secret is a base64url-encoded random 32-byte key. After changing secrets, deploy a saved version to apply the new environment revision.

Sessions last eight hours and are origin- and credential-bound HMAC tokens in a `__Host-` cookie with Secure, HttpOnly and SameSite=Strict. Every POST requires the exact site Origin. Login bodies are limited to 4 KiB; missing configuration fails closed. No password or session token is stored in browser localStorage. Logout clears the browser cookie and form state; individual copied tokens cannot be revoked in this stateless design. Rotating the session secret or password hash revokes all previous sessions. The bounded login-attempt limit is best effort per Worker isolate, not a globally coordinated rate limit.

`npm test` runs authentication and Worker route tests using synthetic credentials. Local `npm run dev` has no owner credentials by default and exposes the demo only; the original Python application remains a separate full local workflow bound to loopback by `START.cmd`. Do not expose that local development server to the internet as a replacement for this authenticated Worker.

## Source attribution

- CDC, Behavioral Risk Factor Surveillance System, 2023: https://www.cdc.gov/brfss/annual_data/annual_2023.html. Local source version fingerprints are retained in the original project's reports; the current website may offer a revised dataset.
- Janosi, A., Steinbrunn, W., Pfisterer, M., and Detrano, R. Heart Disease (1989), UCI Machine Learning Repository. https://doi.org/10.24432/C52P4X. CC BY 4.0; the source permits sharing and adaptation with attribution. The project uses the documented Cleveland predictor subset, transforms its features, and trains classifiers.
- DejaVu Sans is embedded in PDF reports; see `assets/FONT_LICENSE.txt`.

This is a research application, not a clinical diagnostic service or a validated forecast of a future cardiovascular event. No independent clinical or Kazakhstan population validation has been performed.
