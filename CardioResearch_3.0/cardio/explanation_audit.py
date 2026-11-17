"""Offline audit of the deployed permutation estimator, not a new predictor.

Exact refers to enumeration of coalitions for a finite empirical background.
It does not mean causal attribution or an exact population explanation.
"""
from math import comb
import numpy as np


def coalition_values(predict, background, x, batch_coalitions=128):
    background = np.asarray(background, dtype=float)
    x = np.asarray(x, dtype=float)
    if background.ndim != 2 or not len(background) or x.shape != (background.shape[1],):
        raise ValueError('Expected a nonempty background matrix and one matching row')
    d = len(x)
    if not 1 <= d <= 15 or batch_coalitions < 1:
        raise ValueError('Exact enumeration limited to 1–15 features and positive batches')
    values = np.empty(1 << d)
    for start in range(0, len(values), batch_coalitions):
        ids = np.arange(start, min(start + batch_coalitions, len(values)))
        mask = (ids[:, None] & (1 << np.arange(d))) != 0
        blocks = np.where(mask[:, None, :], x[None, None, :], background[None, :, :])
        p = np.asarray(predict(blocks.reshape(-1, d)), dtype=float)
        if p.shape != (len(ids) * len(background),) or not np.isfinite(p).all():
            raise ValueError('Predictor must return one finite score per row')
        values[ids] = p.reshape(len(ids), len(background)).mean(axis=1)
    return values


def exact_from_values(values):
    values = np.asarray(values, dtype=float)
    d = (len(values) - 1).bit_length()
    if d < 1 or len(values) != 1 << d:
        raise ValueError('Expected a power-of-two coalition table')
    result = np.zeros(d)
    for j in range(d):
        for subset in range(len(values)):
            if not subset & (1 << j):
                result[j] += (values[subset | (1 << j)] - values[subset]) / (d * comb(d - 1, subset.bit_count()))
    return result


def sampled_from_values(values, permutations=48, seed=20261107):
    """Same forward/reverse RNG schedule as cardio.explain, cached game values."""
    if permutations < 2 or permutations % 2:
        raise ValueError('Use a positive even permutation budget')
    d = (len(values) - 1).bit_length()
    if len(values) != 1 << d:
        raise ValueError('Invalid coalition table')
    rng = np.random.default_rng(seed)
    result = np.zeros(d)
    for _ in range(permutations // 2):
        order = rng.permutation(d)
        for seq in (order, order[::-1]):
            subset = 0
            for j in seq:
                next_subset = subset | (1 << int(j))
                result[j] += values[next_subset] - values[subset]
                subset = next_subset
    return result / permutations


def comparison(exact, approx):
    exact, approx = np.asarray(exact), np.asarray(approx)
    k = min(3, len(exact))
    top_exact = set(np.argsort(-np.abs(exact), kind='stable')[:k])
    top_approx = set(np.argsort(-np.abs(approx), kind='stable')[:k])
    relevant = np.abs(exact) >= 1e-4  # 0.01 percentage points, fixed in protocol
    return {'mae_pp': float(np.mean(np.abs(exact - approx)) * 100),
            'max_error_pp': float(np.max(np.abs(exact - approx)) * 100),
            'top3_overlap': len(top_exact & top_approx) / k,
            'sign_agreement': float(np.mean(np.sign(exact[relevant]) == np.sign(approx[relevant]))) if relevant.any() else None}
