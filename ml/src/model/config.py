"""Shared CPU LightGBM settings for offline, live, and walk-forward fits.

Predictive hyperparameters are unchanged; the execution settings fix row sampling,
thread count and histogram construction for reproducible fits in a fixed runtime.
"""
LGBM_PARAMS = dict(
    n_estimators=200, learning_rate=0.05, num_leaves=15, max_depth=4,
    min_child_samples=40, subsample=0.8, colsample_bytree=0.8,
    reg_lambda=1.0, random_state=42, verbosity=-1,
    device_type="cpu", n_jobs=1, deterministic=True, force_col_wise=True,
)
