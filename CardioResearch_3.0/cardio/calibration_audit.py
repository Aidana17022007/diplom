"""Descriptive frozen-prediction diagnostics; no recalibration is applied."""
import numpy as np
from scipy.optimize import brentq, minimize
from scipy.special import expit, logit
from sklearn.metrics import average_precision_score, roc_auc_score, precision_score


def calibration_diagnostics(y, probability):
    y, p = np.asarray(y, dtype=float), np.asarray(probability, dtype=float)
    if y.ndim != 1 or p.shape != y.shape or not np.isfinite(p).all() or not np.isin(y, [0, 1]).all() or len(np.unique(y)) != 2:
        raise ValueError('Two binary classes and finite matching predictions are required')
    if np.any((p < 0) | (p > 1)):
        raise ValueError('Probabilities must lie in [0,1]')
    z = logit(np.clip(p, 1e-6, 1-1e-6))
    intercept = brentq(lambda a: np.mean(expit(a+z)-y), -50, 50)
    result = {'n': len(y), 'observed_fraction': float(y.mean()), 'mean_probability': float(p.mean()),
              'mean_error_pp': float((p.mean()-y.mean())*100), 'intercept_slope_fixed_1': float(intercept),
              'clipped_predictions': int(((p < 1e-6) | (p > 1-1e-6)).sum())}
    if np.ptp(z) < 1e-10:
        return {**result, 'joint_intercept': None, 'slope': None, 'status': 'constant_scores_slope_unidentifiable'}
    design = np.c_[np.ones(len(z)), z]
    def objective(beta):
        linear = design @ beta
        return np.mean(np.logaddexp(0, linear)-y*linear), design.T@(expit(linear)-y)/len(y)
    fit = minimize(objective, [0., 1.], jac=True, method='BFGS', options={'gtol': 1e-9})
    if not fit.success and np.max(np.abs(fit.jac)) > 1e-7:
        raise RuntimeError(f'Calibration diagnostic fit failed: {fit.message}')
    return {**result, 'joint_intercept': float(fit.x[0]), 'slope': float(fit.x[1]), 'status': 'ok'}


def prior_scenario(y, probability, prevalence, threshold):
    """Class-constant weights preserve empirical score distributions within y."""
    y = np.asarray(y); p = np.asarray(probability)
    observed = np.mean(y)
    if not 0 < prevalence < 1 or not 0 < observed < 1:
        raise ValueError('Prevalence must be between zero and one with both classes')
    weights = np.where(y == 1, prevalence/observed, (1-prevalence)/(1-observed))
    return {'assumed_prevalence': float(prevalence),
            'roc_auc': float(roc_auc_score(y, p, sample_weight=weights)),
            'average_precision': float(average_precision_score(y, p, sample_weight=weights)),
            'precision_fixed_threshold': float(precision_score(y, p >= threshold, sample_weight=weights, zero_division=0))}
