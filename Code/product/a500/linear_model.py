"""Weekly linear factor aggregation with train-only feature screening."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet, Lasso, LinearRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .tree_model import FactorPanel, evaluate_predictions, mean_rank_ic, normalized_predictions, split_fold


@dataclass
class LinearScreenResult:
    indices: list[int]
    report: pd.DataFrame


def _factor_ic_statistics(values: np.ndarray, labels: np.ndarray, dates: np.ndarray,
                          minimum_stocks: int) -> dict[str, float]:
    _, weekly = mean_rank_ic(values, labels, dates, minimum_stocks)
    ic = weekly.rank_ic.dropna() if len(weekly) else pd.Series(dtype=float)
    std = ic.std(ddof=1) if len(ic) > 1 else np.nan
    mean = ic.mean() if len(ic) else np.nan
    return {
        'ic_weeks': int(len(ic)),
        'rank_ic_mean': float(mean) if np.isfinite(mean) else np.nan,
        'rank_ic_abs': float(abs(mean)) if np.isfinite(mean) else np.nan,
        'rank_icir': float(mean / std) if np.isfinite(std) and std > 0 else np.nan,
        'oriented_positive_share': float(max((ic > 0).mean(), (ic < 0).mean())) if len(ic) else np.nan,
    }


def _percentile_score(series: pd.Series) -> pd.Series:
    finite = series.replace([np.inf, -np.inf], np.nan)
    return finite.rank(method='average', pct=True).fillna(0.0)


def screen_linear_features(panel: FactorPanel, train_mask: np.ndarray, config: dict,
                           quality_summary: pd.DataFrame | None = None) -> LinearScreenResult:
    """Rank factors using train-only IC plus the fixed 2020–2022 single-factor report.

    The final greedy pass rejects a factor whenever its absolute correlation with
    any already-selected, better-ranked factor exceeds the configured ceiling.
    """
    X = panel.features[train_mask]
    labels = panel.samples.label[train_mask].to_numpy(dtype=float)
    dates = panel.samples.signal_date[train_mask].to_numpy()
    unique_dates = pd.DatetimeIndex(np.unique(dates))
    date_positions = [np.flatnonzero(dates == date) for date in unique_dates]
    records: list[dict] = []
    for j, name in enumerate(panel.feature_names):
        col = X[:, j].astype(float, copy=False)
        finite = np.isfinite(col)
        coverage = float(finite.mean()) if len(col) else 0.0
        valid_weeks = sum(
            np.isfinite(col[pos]).sum() >= config['minimum_stocks_per_week'] and
            np.nanmin(col[pos]) < np.nanmax(col[pos])
            for pos in date_positions
        )
        valid_share = valid_weeks / len(unique_dates) if len(unique_dates) else 0.0
        stats = _factor_ic_statistics(col, labels, dates, config['minimum_stocks_per_week'])
        passes = (
            coverage >= config['minimum_train_coverage'] and
            valid_share >= config['minimum_valid_week_share'] and
            stats['ic_weeks'] >= config['minimum_ic_weeks'] and
            stats['rank_ic_abs'] >= config['minimum_abs_rank_ic']
        )
        records.append({
            'factor': name, 'feature_index': j, 'train_coverage': coverage,
            'valid_week_share': valid_share, 'valid_weeks': valid_weeks,
            'quality_gate': passes, **stats,
        })
    report = pd.DataFrame(records)
    if quality_summary is not None and not quality_summary.empty:
        auxiliary = quality_summary.copy()
        keep = ['factor', 'net_sharpe', 'net_annual_return', 'rank_ic_positive_share']
        auxiliary = auxiliary[[c for c in keep if c in auxiliary]].drop_duplicates('factor')
        report = report.merge(auxiliary, on='factor', how='left', suffixes=('', '_single_factor'))
    for col in ['net_sharpe', 'net_annual_return', 'rank_ic_positive_share']:
        if col not in report:
            report[col] = np.nan

    direction_metric = config.get('factor_direction_metric')
    report['factor_direction'] = 1.0
    if direction_metric:
        if direction_metric not in report:
            raise ValueError(f'因子方向指标不存在: {direction_metric}')
        report['factor_direction'] = np.where(report[direction_metric].lt(0), -1.0, 1.0)

    weights = config['ranking_weights']
    return_metric = report.net_annual_return * report.factor_direction
    sharpe_metric = report.net_sharpe * report.factor_direction
    if config.get('single_factor_return_use_absolute', True):
        return_metric = return_metric.abs()
    if config.get('single_factor_sharpe_use_absolute', True):
        sharpe_metric = sharpe_metric.abs()
    report['selection_score'] = (
        weights['abs_rank_ic'] * _percentile_score(report.rank_ic_abs) +
        weights['abs_rank_icir'] * _percentile_score(report.rank_icir.abs()) +
        weights['ic_direction_stability'] * _percentile_score(report.oriented_positive_share) +
        weights['single_factor_sharpe'] * _percentile_score(sharpe_metric) +
        weights['single_factor_return'] * _percentile_score(return_metric)
    )
    report['selected'] = False
    report['reason'] = np.where(report.quality_gate, 'CORRELATION_OR_CAP', 'QUALITY_OR_IC_GATE')
    report['max_abs_corr_to_selected'] = np.nan
    candidates = report[report.quality_gate].sort_values(
        ['selection_score', 'rank_ic_abs', 'factor'], ascending=[False, False, True], kind='stable')
    if candidates.empty:
        raise ValueError('训练窗口内没有因子通过覆盖率、有效周和 IC 下限')

    candidate_indices = candidates.feature_index.astype(int).tolist()
    sample_limit = int(config.get('correlation_sample_rows', 100_000))
    if len(X) > sample_limit:
        sampled_rows = np.linspace(0, len(X) - 1, sample_limit, dtype=int)
        corr_values = X[sampled_rows][:, candidate_indices]
    else:
        corr_values = X[:, candidate_indices]
    corr = pd.DataFrame(corr_values, columns=candidate_indices).corr(min_periods=100).abs()
    ceiling = float(config['maximum_abs_pairwise_correlation'])
    maximum = int(config['maximum_selected_factors'])
    selected: list[int] = []
    for row in candidates.itertuples():
        idx = int(row.feature_index)
        max_corr = float(corr.loc[idx, selected].max()) if selected else 0.0
        report.loc[report.feature_index == idx, 'max_abs_corr_to_selected'] = max_corr
        if len(selected) >= maximum:
            report.loc[report.feature_index == idx, 'reason'] = 'MAX_FEATURE_CAP'
        elif max_corr > ceiling:
            report.loc[report.feature_index == idx, 'reason'] = 'CORRELATION_GATE'
        else:
            selected.append(idx)
            report.loc[report.feature_index == idx, ['selected', 'reason']] = [True, 'SELECTED']
    if not selected:
        raise ValueError('相关性约束后没有剩余因子')
    return LinearScreenResult(selected, report)


def _estimator(model_name: str, params: dict, config: dict):
    common = dict(max_iter=config['max_iter'], tol=config['tolerance'], selection='cyclic')
    if model_name == 'ridge':
        return Ridge(alpha=float(params['alpha']))
    if model_name == 'elastic_net':
        return ElasticNet(alpha=float(params['alpha']), l1_ratio=float(params['l1_ratio']), **common)
    if model_name == 'lasso':
        return Lasso(alpha=float(params['alpha']), **common)
    if model_name == 'ols':
        return LinearRegression()
    raise ValueError(f'未知线性模型: {model_name}')


def make_pipeline(model_name: str, params: dict, config: dict) -> Pipeline:
    return Pipeline([
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler()),
        ('model', _estimator(model_name, params, config)),
    ])


def candidate_grid(model_name: str, config: dict) -> list[dict]:
    if model_name == 'ridge':
        return [{'alpha': x} for x in config['ridge_alphas']]
    if model_name == 'lasso':
        return [{'alpha': x} for x in config['lasso_alphas']]
    if model_name == 'elastic_net':
        return [{'alpha': a, 'l1_ratio': r}
                for a in config['elastic_net_alphas'] for r in config['elastic_net_l1_ratios']]
    if model_name == 'ols':
        return [{}]
    raise ValueError(f'未知线性模型: {model_name}')


def _coefficient_rows(pipeline: Pipeline, names: list[str], fold_id: int,
                      model_name: str) -> list[dict]:
    coef = np.asarray(pipeline.named_steps['model'].coef_, dtype=float).ravel()
    return [dict(fold_id=fold_id, model_name=model_name, factor=name,
                 coefficient=float(value), abs_coefficient=float(abs(value)),
                 coefficient_sign=int(np.sign(value)))
            for name, value in zip(names, coef)]


def run_linear_folds(panel: FactorPanel, config: dict, output_dir: Path, model_dir: Path,
                     run_label: str, quality_summary: pd.DataFrame | None = None,
                     test_years: list[int] | None = None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    years = test_years or list(range(config['first_test_year'], config['last_test_year'] + 1))
    predictions_all, screen_rows, candidate_rows = [], [], []
    coefficient_rows, fold_rows = [], []
    config_id = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:8]
    for year in years:
        masks = split_fold(panel.samples, year, config['first_train_year'])
        train_weeks = panel.samples.signal_date[masks['train']].nunique()
        if train_weeks < config['minimum_train_weeks']:
            raise ValueError(f'{year} 年折只有 {train_weeks} 个训练周')
        screen = screen_linear_features(panel, masks['train'], config, quality_summary)
        fold_screen = screen.report.copy()
        fold_screen.insert(0, 'fold_id', str(year))
        screen_rows.append(fold_screen)
        selected = screen.indices
        names = [panel.feature_names[j] for j in selected]
        directions = screen.report.set_index('feature_index').loc[selected, 'factor_direction'].to_numpy(dtype=float)
        x_train = panel.features[masks['train']][:, selected] * directions
        y_train = panel.samples.target[masks['train']].to_numpy(dtype=float)
        x_val = panel.features[masks['validation']][:, selected] * directions
        y_val_raw = panel.samples.label[masks['validation']].to_numpy(dtype=float)
        d_val = panel.samples.signal_date[masks['validation']].to_numpy()
        if not len(x_val) or not masks['test'].any():
            raise ValueError(f'{year} 年验证或测试样本为空')
        for model_name in config['models']:
            best_pipeline, best_params, best_score = None, None, -np.inf
            for candidate_id, params in enumerate(candidate_grid(model_name, config)):
                pipeline = make_pipeline(model_name, params, config)
                pipeline.fit(x_train, y_train)
                val_prediction = pipeline.predict(x_val)
                score, _ = mean_rank_ic(val_prediction, y_val_raw, d_val,
                                        config['minimum_stocks_per_week'])
                candidate_rows.append(dict(fold_id=year, model_name=model_name,
                                           candidate_id=candidate_id,
                                           validation_rank_ic=score, **params))
                comparable = score if np.isfinite(score) else -np.inf
                if comparable > best_score:
                    best_pipeline, best_params, best_score = pipeline, params, comparable
            if best_pipeline is None:
                raise ValueError(f'{year} 年 {model_name} 没有有效验证结果')
            model_id = f'{model_name}_{run_label}_{config_id}'
            joblib.dump(best_pipeline, model_dir / f'{model_id}_{year}.joblib')
            pred_mask = masks['predict'] & np.isfinite(panel.features[:, selected]).any(axis=1)
            prediction = panel.samples.loc[pred_mask].copy()
            prediction['prediction'] = best_pipeline.predict(
                panel.features[pred_mask][:, selected] * directions)
            prediction = normalized_predictions(prediction)
            prediction['model_name'] = model_name
            prediction['model_id'] = model_id
            prediction['fold_id'] = str(year)
            prediction['train_end_date'] = panel.samples.target_end_date[masks['train']].max()
            prediction['data_mode'] = run_label
            predictions_all.append(prediction)
            coefficient_rows.extend(_coefficient_rows(best_pipeline, names, year, model_name))
            fold_rows.append(dict(fold_id=year, model_name=model_name, model_id=model_id,
                                  validation_rank_ic=best_score, best_parameters=json.dumps(best_params),
                                  n_features=len(names), train_rows=len(x_train),
                                  validation_rows=len(x_val), test_predictions=len(prediction),
                                  train_end_date=prediction.train_end_date.max()))
        print(f'completed linear test year {year}: {len(names)} factors', flush=True)

    predictions = pd.concat(predictions_all, ignore_index=True)
    weekly_outputs, evaluation_rows = [], []
    for model_id, subset in predictions.groupby('model_id'):
        weekly, metrics = evaluate_predictions(
            subset, config['minimum_stocks_per_week'], config['cost_bps_one_way'],
            config['portfolio_tail_fraction'])
        weekly.insert(0, 'model_id', model_id)
        weekly_outputs.append(weekly)
        evaluation_rows.append(dict(model_id=model_id, **metrics))
    weekly_all = pd.concat(weekly_outputs, ignore_index=True)
    yearly_rows = []
    for (model_id, year), group in weekly_all.groupby(['model_id', weekly_all.signal_date.dt.year]):
        ic = group.rank_ic.dropna()
        good = group[group.status == 'OK']
        yearly_rows.append(dict(
            model_id=model_id, test_year=int(year), weeks=len(good),
            rank_ic_mean=float(ic.mean()) if len(ic) else np.nan,
            rank_icir=float(ic.mean()/ic.std(ddof=1)) if len(ic)>1 and ic.std(ddof=1)>0 else np.nan,
            rank_ic_positive_share=float((ic > 0).mean()) if len(ic) else np.nan,
            net_return=float((1 + good.net_return).prod() - 1) if len(good) else np.nan,
            turnover_mean=float(good.one_way_turnover.mean()) if len(good) else np.nan))

    coefficients = pd.DataFrame(coefficient_rows)
    stability = coefficients.groupby(['model_name', 'factor']).agg(
        coefficient_mean=('coefficient', 'mean'), coefficient_std=('coefficient', 'std'),
        abs_coefficient_mean=('abs_coefficient', 'mean'),
        positive_share=('coefficient', lambda x: float((x > 0).mean())),
        folds=('fold_id', 'nunique')).reset_index()
    predictions.to_parquet(output_dir / 'oos_predictions.parquet', index=False)
    pd.concat(screen_rows, ignore_index=True).to_csv(output_dir / 'feature_screen.csv', index=False)
    pd.DataFrame(candidate_rows).to_csv(output_dir / 'validation_candidates.csv', index=False)
    pd.DataFrame(fold_rows).to_csv(output_dir / 'fold_models.csv', index=False)
    coefficients.to_csv(output_dir / 'factor_coefficients.csv', index=False)
    stability.to_csv(output_dir / 'coefficient_stability.csv', index=False)
    weekly_all.to_csv(output_dir / 'weekly_evaluation.csv', index=False)
    pd.DataFrame(yearly_rows).to_csv(output_dir / 'yearly_evaluation.csv', index=False)
    pd.DataFrame(evaluation_rows).to_csv(output_dir / 'evaluation_summary.csv', index=False)
    (output_dir / 'run_config.json').write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding='utf-8')
    write_linear_report(output_dir, run_label)


def write_linear_report(output_dir: Path, run_label: str) -> None:
    overall = pd.read_csv(output_dir / 'evaluation_summary.csv')
    yearly = pd.read_csv(output_dir / 'yearly_evaluation.csv')
    folds = pd.read_csv(output_dir / 'fold_models.csv')
    lines = [f'# 线性因子聚合模型：{run_label}', '',
             'Ridge 为基准、Elastic Net 为主模型，并同时报告 Lasso 与普通多元线性回归。'
             '四个模型统一采用 MSE；正则化模型仅使用验证期选择参数。', '',
             '## 外层测试汇总', '',
             '| 模型 | 周数 | Rank IC | Rank ICIR | 年化 ICIR | 正 IC 比例 | 成本后年化收益 | 最大回撤 | 换手 |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for _, row in overall.iterrows():
        name = row.model_id.split('_')[0] if not row.model_id.startswith('elastic_net') else 'elastic_net'
        lines.append(f'| {name} | {int(row.weeks)} | {row.rank_ic_mean:.4f} | {row.rank_icir:.3f} | '
                     f'{row.rank_icir_annualized:.3f} | {row.rank_ic_positive_share:.1%} | '
                     f'{row.net_annual_return:.1%} | {row.net_max_drawdown:.1%} | {row.turnover_mean:.1%} |')
    lines += ['', '## 每折选择', '',
              '| 测试年 | 模型 | 因子数 | 验证 Rank IC | 最优参数 |', '|---:|---|---:|---:|---|']
    for _, row in folds.iterrows():
        lines.append(f'| {row.fold_id} | {row.model_name} | {row.n_features} | '
                     f'{row.validation_rank_ic:.4f} | `{row.best_parameters}` |')
    lines += ['', '## 分年稳定性', '',
              '| 模型 | 年份 | 周数 | Rank IC | ICIR | 正 IC 比例 | 成本后收益 | 换手 |',
              '|---|---:|---:|---:|---:|---:|---:|---:|']
    for _, row in yearly.iterrows():
        lines.append(f'| {row.model_id} | {int(row.test_year)} | {int(row.weeks)} | '
                     f'{row.rank_ic_mean:.4f} | {row.rank_icir:.3f} | '
                     f'{row.rank_ic_positive_share:.1%} | {row.net_return:.1%} | {row.turnover_mean:.1%} |')
    lines += ['', '## 口径说明', '',
              '- 因子筛选仅使用每折训练期：覆盖率、有效周、绝对 Rank IC 下限、ICIR和方向稳定性。',
              '- 2020–2022 单因子成本后 Sharpe 与收益只作为同分候选的辅助排名信息。',
              '- 高排名因子优先进入；若与已入选因子的绝对相关系数超过阈值则剔除。',
              '- 当前线性模型统一使用 MSE，而非 Huber loss；这是为了保持 Ridge、Elastic Net、Lasso 和 OLS 的标准定义。',
              '- 外层测试结果只评价，不反向修改筛选阈值、模型或参数范围。', '']
    (output_dir / 'model_report.md').write_text('\n'.join(lines), encoding='utf-8')
