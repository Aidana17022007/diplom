"""Interventional Shapley estimation by permutation sampling.

No neural/causal interpretation: missing coalitions are replaced with a fixed
training background. Forward/reverse pairs and a fixed seed make the estimate
reproducible. Completeness holds up to numerical precision by telescoping.
This is a direct SHAP-value estimator, not a call to the external shap package.
"""
import numpy as np
import pandas as pd

def permutation_shap(predict,background,x,permutations=48,seed=20261107):
    background=np.asarray(background,dtype=float); x=np.asarray(x,dtype=float).reshape(-1)
    n,d=background.shape; rng=np.random.default_rng(seed); orders=[]
    for _ in range(permutations//2):
        order=rng.permutation(d);orders.extend([order,order[::-1]])
    values=np.zeros(d)
    for order in orders:
        masked=background.copy(); blocks=[masked.copy()]
        for j in order:
            masked[:,j]=x[j];blocks.append(masked.copy())
        predictions=predict(np.concatenate(blocks,axis=0)).reshape(d+1,n).mean(axis=1)
        values[order]+=np.diff(predictions)
    return values/len(orders),float(np.mean(predict(background)))
