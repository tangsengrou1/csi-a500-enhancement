"""LightGBM训练折内质量筛选：覆盖率、有效周数和截面变异。
最终Ridge使用的IC/相关性筛选实现位于 `a500/linear_model.py`；本模块仍负责树模型的通用质量筛选。
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import math
import numpy as np
import pandas as pd
from feature_engineering import FactorPanel

def screen_features(panel: FactorPanel, train_mask: np.ndarray, config: dict) -> tuple[list[int], pd.DataFrame]:
    dates = panel.samples.signal_date.to_numpy()[train_mask]
    X = panel.features[train_mask]
    unique_dates = pd.DatetimeIndex(np.unique(dates))
    date_positions = [np.flatnonzero(dates == date) for date in unique_dates]
    records = []
    selected = []
    for j, name in enumerate(panel.feature_names):
        col = X[:, j]
        finite = np.isfinite(col)
        coverage = float(finite.mean()) if len(col) else 0.0
        valid_weeks = 0
        for positions in date_positions:
            values = col[positions]
            values = values[np.isfinite(values)]
            valid_weeks += len(values) >= 2 and values.min() < values.max()
        share = valid_weeks / len(unique_dates) if len(unique_dates) else 0.0
        usable = valid_weeks > 0
        keep = usable if config['feature_policy'] == 'all_usable' else (
            usable and coverage >= config['minimum_train_coverage'] and
            share >= config['minimum_valid_week_share'])
        records.append(dict(factor=name, train_coverage=coverage, valid_week_share=share,
                            valid_weeks=valid_weeks, selected=keep,
                            reason='SELECTED' if keep else ('NO_VARIATION' if not usable else 'QUALITY_GATE')))
        if keep:
            selected.append(j)
    if not selected:
        raise ValueError('训练窗口内没有通过质量筛选的因子')
    return selected, pd.DataFrame(records)
