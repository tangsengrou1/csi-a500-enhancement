"""训练样本、周频标签与截面预处理；不读取测试期收益筛选因子。"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import math
import numpy as np
import pandas as pd

@dataclass
class FactorPanel:
    features: np.ndarray
    feature_names: list[str]
    samples: pd.DataFrame
    signal_dates: pd.DatetimeIndex
    securities: pd.Index



def weekly_schedule(dates: pd.DatetimeIndex) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    dates = pd.DatetimeIndex(dates).sort_values().unique()
    dates = dates[dates.dayofweek < 5]
    signals = dates.to_series().groupby(dates.to_period('W-FRI')).max().tolist()
    positions = {date: pos for pos, date in enumerate(dates)}
    return [(a, dates[positions[a] + 1], dates[positions[b] + 1])
            for a, b in zip(signals[:-1], signals[1:]) if positions[b] + 1 < len(dates)]



def cross_section_rank(values: pd.DataFrame, lower: float, upper: float) -> pd.DataFrame:
    """Clip at same-date quantiles, then map average ranks exactly to [0, 1]."""
    values = values.replace([np.inf, -np.inf], np.nan)
    lo = values.quantile(lower, axis=1)
    hi = values.quantile(upper, axis=1)
    clipped = values.clip(lower=lo, upper=hi, axis=0)
    rank = clipped.rank(axis=1, method='average')
    count = clipped.notna().sum(axis=1)
    return rank.sub(1).div(count.sub(1).where(count > 1), axis=0)



def make_training_target(raw_returns: np.ndarray, mode: str) -> np.ndarray:
    """Transform same-week labels without using later weeks or changing backtest returns."""
    target = np.asarray(raw_returns, dtype=float).copy()
    if mode == 'raw':
        return target
    if mode == 'clipped_relative':
        lower = np.nanquantile(target, .01, axis=1, keepdims=True)
        upper = np.nanquantile(target, .99, axis=1, keepdims=True)
        target = np.clip(target, lower, upper)
    elif mode != 'relative':
        raise ValueError(f'未知收益标签模式: {mode}')
    return target - np.nanmean(target, axis=1, keepdims=True)



def _historical_membership(path: Path, dates: pd.DatetimeIndex, securities: pd.Index) -> np.ndarray:
    c = pd.read_csv(path) if path.suffix.lower() == '.csv' else pd.read_parquet(path)
    date_col = 'date' if 'date' in c else 'effective_date'
    code_col = 'wind_code' if 'wind_code' in c else 'securityID'
    if date_col not in c or code_col not in c:
        raise ValueError('历史成分股必须包含 date/effective_date 和 wind_code/securityID')
    c[date_col] = pd.to_datetime(c[date_col]).dt.normalize()
    c[code_col] = c[code_col].astype(str)
    if 'is_member' in c:
        c = c[c.is_member.astype(bool)]
    snapshot_dates = pd.DatetimeIndex(sorted(c[date_col].unique()))
    if snapshot_dates.empty or dates.min() < snapshot_dates.min():
        raise ValueError('历史成分股快照未覆盖训练期起点')
    grouped = {date: set(g[code_col]) for date, g in c.groupby(date_col)}
    mask = np.zeros((len(dates), len(securities)), dtype=bool)
    for i, signal in enumerate(dates):
        asof = snapshot_dates[snapshot_dates <= signal].max()
        mask[i] = securities.isin(grouped[asof])
    return mask



def build_panel(market_path: Path, factor_store: Path, config: dict,
                constituents_path: Path | None = None, development_universe: bool = False,
                factor_limit: int | None = None) -> FactorPanel:
    if constituents_path is None and not development_universe:
        raise ValueError('正式运行需要历史 A500 成分股文件；仅调试可显式传 --development-universe')
    market = pd.read_parquet(market_path, columns=['securityID', 'trade_dt', 'close', 'amt'])
    market['trade_dt'] = pd.to_datetime(market.trade_dt).dt.normalize()
    market = market[market.trade_dt.dt.dayofweek < 5]
    if market.duplicated(['trade_dt', 'securityID']).any():
        raise ValueError('行情存在重复的日期与证券代码')
    close = market.pivot(index='trade_dt', columns='securityID', values='close').sort_index()
    schedule = weekly_schedule(close.index)
    signal_dates = pd.DatetimeIndex([x[0] for x in schedule])
    securities = close.columns
    n_dates, n_stocks = len(schedule), len(securities)
    if constituents_path is None:
        membership = close.loc[signal_dates].notna().to_numpy()
    else:
        membership = _historical_membership(constituents_path, signal_dates, securities)
        membership &= close.loc[signal_dates].notna().to_numpy()
    paths = sorted((factor_store / 'alpha158_values').glob('*.parquet'))
    paths += sorted((factor_store / 'gtja191_values').glob('*.parquet'))
    if factor_limit is not None:
        paths = paths[:factor_limit]
    names = [p.stem for p in paths]
    if not names or len(names) != len(set(names)):
        raise ValueError('因子文件缺失或因子名重复')
    X = np.full((n_dates * n_stocks, len(paths)), np.nan, dtype=np.float32)
    for j, path in enumerate(paths):
        matrix = pd.read_parquet(path)
        matrix.index = pd.to_datetime(matrix.index).normalize()
        matrix = matrix.reindex(index=signal_dates, columns=securities)
        matrix = matrix.where(membership)
        ranked = cross_section_rank(matrix, config['winsorize_lower'], config['winsorize_upper'])
        X[:, j] = ranked.to_numpy(dtype=np.float32).ravel()
    entries = close.loc[[x[1] for x in schedule]].to_numpy(dtype=float)
    exits = close.loc[[x[2] for x in schedule]].to_numpy(dtype=float)
    with np.errstate(divide='ignore', invalid='ignore'):
        labels = exits / entries - 1
    labels[(entries <= 0) | (exits <= 0) | ~np.isfinite(labels) | ~membership] = np.nan
    target = make_training_target(labels, config.get('label_mode', 'raw'))
    meta = pd.DataFrame({
        'signal_date': np.repeat(signal_dates.to_numpy(), n_stocks),
        'execution_date': np.repeat([x[1] for x in schedule], n_stocks),
        'target_end_date': np.repeat([x[2] for x in schedule], n_stocks),
        'wind_code': np.tile(securities.to_numpy(), n_dates),
        'in_universe': membership.ravel(),
        'label': labels.ravel(),
        'target': target.ravel(),
        'entry_price': entries.ravel(),
        'exit_price': exits.ravel(),
    })
    return FactorPanel(X, names, meta, signal_dates, securities)



def split_fold(samples: pd.DataFrame, test_year: int, first_train_year: int = 2020) -> dict[str, np.ndarray]:
    signal = samples.signal_date
    target_end = samples.target_end_date
    validation_year = test_year - 1
    first_val = signal[signal.dt.year == validation_year].min()
    first_test = signal[signal.dt.year == test_year].min()
    if pd.isna(first_val) or pd.isna(first_test):
        raise ValueError(f'{test_year} 年验证或测试期不存在')
    eligible = samples.in_universe.to_numpy() & np.isfinite(samples.label.to_numpy(dtype=float))
    return {
        'train': eligible & (signal.dt.year.to_numpy() >= first_train_year) &
                 (signal.dt.year.to_numpy() < validation_year) & (target_end.to_numpy() < first_val),
        'validation': eligible & (signal.dt.year.to_numpy() == validation_year) &
                      (target_end.to_numpy() < first_test),
        'test': eligible & (signal.dt.year.to_numpy() == test_year),
        'predict': samples.in_universe.to_numpy() & (signal.dt.year.to_numpy() == test_year),
    }
