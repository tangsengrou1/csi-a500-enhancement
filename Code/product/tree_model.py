"""逐年滚动LightGBM训练、验证期参数选择及测试期评价。"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import math
import numpy as np
import pandas as pd
import lightgbm as lgb
from feature_engineering import FactorPanel, build_panel, split_fold
from factor_screening import screen_features

def mean_rank_ic(scores: np.ndarray, labels: np.ndarray, dates: np.ndarray,
                 minimum_stocks: int = 20) -> tuple[float, pd.DataFrame]:
    frame = pd.DataFrame({'date': dates, 'prediction': scores, 'label': labels})
    records = []
    for date, g in frame.groupby('date', sort=True):
        g = g.replace([np.inf, -np.inf], np.nan).dropna()
        if len(g) < minimum_stocks or g.prediction.nunique() < 2 or g.label.nunique() < 2:
            continue
        records.append(dict(signal_date=date, n=len(g), rank_ic=g.prediction.corr(g.label, method='spearman'),
                            pearson_ic=g.prediction.corr(g.label)))
    out = pd.DataFrame(records)
    return (float(out.rank_ic.mean()) if len(out) else np.nan), out



def ranking_relevance(labels: np.ndarray, dates: np.ndarray) -> tuple[np.ndarray, list[int]]:
    if np.any(dates[:-1] > dates[1:]):
        raise ValueError('排序模型输入必须按信号日期连续排列')
    frame = pd.DataFrame({'date': dates, 'label': labels})
    percentile = frame.groupby('date', sort=False).label.rank(method='average', pct=True)
    relevance = np.minimum(4, np.floor(percentile.to_numpy() * 5).astype(np.int32))
    group = frame.groupby('date', sort=False).size().tolist()
    return relevance, group



def train_candidate(X_train: np.ndarray, y_train: np.ndarray, date_train: np.ndarray,
                    X_val: np.ndarray, y_val: np.ndarray, date_val: np.ndarray,
                    names: list[str], objective: str, candidate: dict, config: dict) -> lgb.Booster:
    params = dict(candidate)
    params.update(verbosity=-1, seed=config['seed'], feature_fraction_seed=config['seed'],
                  bagging_seed=config['seed'], num_threads=config['num_threads'],
                  deterministic=True, force_col_wise=True)
    if objective == 'huber':
        params.update(objective='huber', metric='l2', alpha=0.9)
        train_set = lgb.Dataset(X_train, label=y_train, feature_name=names)
        val_set = lgb.Dataset(X_val, label=y_val, reference=train_set, feature_name=names)
    elif objective == 'lambdarank':
        rel_train, group_train = ranking_relevance(y_train, date_train)
        rel_val, group_val = ranking_relevance(y_val, date_val)
        params.update(objective='lambdarank', metric='ndcg', ndcg_eval_at=[10, 50],
                      label_gain=[0, 1, 3, 7, 15])
        train_set = lgb.Dataset(X_train, label=rel_train, group=group_train, feature_name=names)
        val_set = lgb.Dataset(X_val, label=rel_val, group=group_val, reference=train_set, feature_name=names)
    else:
        raise ValueError(f'未知训练目标: {objective}')
    if config.get('validation_rounds'):
        return lgb.train(params, train_set, num_boost_round=max(config['validation_rounds']))
    return lgb.train(params, train_set, num_boost_round=config['num_boost_round'],
                     valid_sets=[val_set], valid_names=['validation'],
                     callbacks=[lgb.early_stopping(config['early_stopping_rounds'], verbose=False)])



def normalized_predictions(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    group = out.groupby('signal_date').prediction
    rank = group.rank(method='average')
    count = group.transform('count')
    out['prediction_rank'] = (rank - 1) / (count - 1).where(count > 1)
    mean = group.transform('mean')
    std = group.transform('std').replace(0, np.nan)
    out['prediction_z'] = ((out.prediction - mean) / std).clip(-3, 3)
    return out



def evaluate_predictions(predictions: pd.DataFrame, minimum_stocks: int = 20,
                         cost_bps_one_way: float = 20, tail_fraction: float = .2) -> tuple[pd.DataFrame, dict]:
    """Shared week-by-week signal evaluator for tree and later linear models."""
    previous = pd.Series(dtype=float)
    records = []
    for signal, group in predictions.groupby('signal_date', sort=True):
        g = group[np.isfinite(group.prediction) & group.in_universe &
                  np.isfinite(group.entry_price) & group.entry_price.gt(0)].copy()
        ic, ic_rows = mean_rank_ic(g.prediction.to_numpy(), g.label.to_numpy(),
                                   np.full(len(g), signal), minimum_stocks)
        n_tail = int(np.floor(len(g) * tail_fraction))
        if len(g) < minimum_stocks or n_tail < 1:
            records.append(dict(signal_date=signal, status='INSUFFICIENT_STOCKS', rank_ic=ic))
            continue
        g = g.sort_values(['prediction', 'wind_code'])
        low = g.head(n_tail)
        high = g.tail(n_tail)
        selected = pd.concat([low, high])
        if selected.label.isna().any():
            records.append(dict(signal_date=signal, status='MISSING_EXIT_PRICE', rank_ic=ic))
            continue
        weights = pd.concat([pd.Series(-.5 / n_tail, index=low.wind_code),
                             pd.Series(.5 / n_tail, index=high.wind_code)])
        realized = selected.set_index('wind_code').label
        long_return = float((weights[weights > 0] * realized.reindex(weights[weights > 0].index)).sum())
        short_return = float((weights[weights < 0] * realized.reindex(weights[weights < 0].index)).sum())
        turnover_one_way = float(.5 * weights.sub(previous, fill_value=0).abs().sum())
        cost = turnover_one_way * cost_bps_one_way / 10_000
        records.append(dict(signal_date=signal, status='OK', stocks=len(g),
                            rank_ic=ic, long_return=long_return, short_return=short_return,
                            gross_return=long_return + short_return,
                            one_way_turnover=turnover_one_way, cost=cost,
                            net_return=long_return + short_return - cost))
        previous = weights
    weekly = pd.DataFrame(records)
    ic = weekly.rank_ic.dropna()
    good = weekly[weekly.status == 'OK']
    returns = good.net_return if len(good) else pd.Series(dtype=float)
    nav = (1 + returns).cumprod()
    vol = returns.std(ddof=1) * math.sqrt(52) if len(returns) > 1 else np.nan
    summary = dict(weeks=len(good), rank_ic_mean=float(ic.mean()) if len(ic) else np.nan,
                   rank_icir=float(ic.mean()/ic.std(ddof=1)) if len(ic)>1 and ic.std(ddof=1)>0 else np.nan,
                   rank_icir_annualized=float(ic.mean()/ic.std(ddof=1)*math.sqrt(52)) if len(ic)>1 and ic.std(ddof=1)>0 else np.nan,
                   rank_ic_positive_share=float((ic > 0).mean()) if len(ic) else np.nan,
                   net_cumulative_return=float(nav.iloc[-1]-1) if len(nav) else np.nan,
                   net_annual_return=float(nav.iloc[-1]**(52/len(nav))-1) if len(nav) and nav.iloc[-1]>0 else np.nan,
                   net_annual_vol=float(vol) if np.isfinite(vol) else np.nan,
                   net_sharpe=float(returns.mean()*52/vol) if np.isfinite(vol) and vol>0 else np.nan,
                   net_max_drawdown=float((nav/nav.cummax()-1).min()) if len(nav) else np.nan,
                   turnover_mean=float(good.one_way_turnover.mean()) if len(good) else np.nan,
                   missing_weeks=int((weekly.status != 'OK').sum()))
    return weekly, summary



def run_folds(panel: FactorPanel, config: dict, output_dir: Path, model_dir: Path,
              run_label: str, test_years: list[int] | None = None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    if test_years is None:
        test_years = list(range(config['first_test_year'], config['last_test_year'] + 1))
    all_predictions = []
    candidate_rows = []
    importance_rows = []
    feature_rows = []
    fold_rows = []
    config_id = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:8]
    for year in test_years:
        masks = split_fold(panel.samples, year, config['first_train_year'])
        train_dates = panel.samples.signal_date[masks['train']].nunique()
        if train_dates < config['minimum_train_weeks']:
            raise ValueError(f'{year} 年折只有 {train_dates} 个训练周')
        selected, feature_status = screen_features(panel, masks['train'], config)
        feature_status.insert(0, 'fold_id', str(year))
        feature_rows.append(feature_status)
        names = [panel.feature_names[j] for j in selected]
        x_train = panel.features[masks['train']][:, selected]
        y_train = panel.samples.target[masks['train']].to_numpy(dtype=float)
        d_train = panel.samples.signal_date[masks['train']].to_numpy()
        x_val = panel.features[masks['validation']][:, selected]
        y_val = panel.samples.target[masks['validation']].to_numpy(dtype=float)
        y_val_raw = panel.samples.label[masks['validation']].to_numpy(dtype=float)
        d_val = panel.samples.signal_date[masks['validation']].to_numpy()
        if not len(x_val) or not masks['test'].any():
            raise ValueError(f'{year} 年验证或测试样本为空')
        for objective in config.get('objectives', ['huber', 'lambdarank']):
            best = None
            best_score = -np.inf
            best_index = -1
            best_round = -1
            for index, candidate in enumerate(config['candidates']):
                booster = train_candidate(x_train, y_train, d_train, x_val, y_val, d_val,
                                          names, objective, candidate, config)
                rounds = config.get('validation_rounds') or [booster.best_iteration]
                checkpoint_scores = []
                for iteration in rounds:
                    val_pred = booster.predict(x_val, num_iteration=iteration)
                    score, _ = mean_rank_ic(val_pred, y_val_raw, d_val, config['minimum_stocks_per_week'])
                    checkpoint_scores.append((iteration, score))
                iteration, score = max(checkpoint_scores,
                                       key=lambda pair: pair[1] if np.isfinite(pair[1]) else -np.inf)
                candidate_rows.append(dict(fold_id=year, objective=objective, candidate_id=index,
                                           validation_rank_ic=score, best_iteration=iteration,
                                           **candidate))
                if np.isfinite(score) and score > best_score:
                    best, best_score, best_index, best_round = booster, score, index, iteration
            if best is None:
                raise ValueError(f'{year} 年 {objective} 没有可计算的验证 Rank IC')
            model_id = f'lightgbm_{objective}_{config["feature_policy"]}_{run_label}_{config_id}'
            # LightGBM的C层在Windows中文目录下无法直接save_model；用Python写入同一模型文本。
            (model_dir / f'{model_id}_{year}.txt').write_text(best.model_to_string(), encoding='utf-8')
            pred_mask = masks['predict'] & np.isfinite(panel.features).any(axis=1)
            p = panel.samples.loc[pred_mask].copy()
            p['prediction'] = best.predict(panel.features[pred_mask][:, selected], num_iteration=best_round)
            p = normalized_predictions(p)
            p['model_name'] = f'lightgbm_{objective}'
            p['model_id'] = model_id
            p['fold_id'] = str(year)
            p['train_end_date'] = panel.samples.target_end_date[masks['train']].max()
            p['data_mode'] = run_label
            all_predictions.append(p)
            for name, gain, split in zip(names, best.feature_importance('gain'), best.feature_importance('split')):
                importance_rows.append(dict(fold_id=year, objective=objective, factor=name,
                                            gain=float(gain), split=int(split)))
            fold_rows.append(dict(fold_id=year, objective=objective, model_id=model_id,
                                  selected_candidate=best_index, validation_rank_ic=best_score,
                                  best_iteration=best_round, n_features=len(names),
                                  train_rows=len(x_train), validation_rows=len(x_val),
                                  test_predictions=len(p), train_end_date=p.train_end_date.max()))
        print(f'completed test year {year}: {len(names)} factors', flush=True)
    predictions = pd.concat(all_predictions, ignore_index=True)
    weekly_outputs = []
    evaluation_rows = []
    for model_id, subset in predictions.groupby('model_id'):
        weekly, metrics = evaluate_predictions(subset,
                 config['minimum_stocks_per_week'], config['cost_bps_one_way'],
                 config['portfolio_tail_fraction'])
        weekly.insert(0, 'model_id', model_id)
        weekly_outputs.append(weekly)
        evaluation_rows.append(dict(model_id=model_id, **metrics))
    predictions.to_parquet(output_dir / 'oos_predictions.parquet', index=False)
    pd.concat(feature_rows).to_csv(output_dir / 'feature_screen.csv', index=False)
    pd.DataFrame(candidate_rows).to_csv(output_dir / 'validation_candidates.csv', index=False)
    pd.DataFrame(fold_rows).to_csv(output_dir / 'fold_models.csv', index=False)
    importance = pd.DataFrame(importance_rows)
    importance['gain_share'] = importance.groupby(['fold_id', 'objective']).gain.transform(
        lambda x: x / x.sum() if x.sum() > 0 else x * 0)
    importance['importance_rank'] = importance.groupby(['fold_id', 'objective']).gain.rank(
        ascending=False, method='average')
    importance.to_csv(output_dir / 'feature_importance.csv', index=False)
    importance.groupby(['objective', 'factor']).agg(gain_share_mean=('gain_share', 'mean'),
        gain_share_std=('gain_share', 'std'), importance_rank_mean=('importance_rank', 'mean'),
        importance_rank_std=('importance_rank', 'std'), folds=('fold_id', 'nunique')).reset_index().to_csv(
            output_dir / 'feature_importance_stability.csv', index=False)
    weekly_all = pd.concat(weekly_outputs, ignore_index=True)
    weekly_all.to_csv(output_dir / 'weekly_evaluation.csv', index=False)
    yearly_rows = []
    for (model_id, year), group in weekly_all.groupby(['model_id', weekly_all.signal_date.dt.year]):
        ic = group.rank_ic.dropna()
        good = group[group.status == 'OK']
        yearly_rows.append(dict(model_id=model_id, test_year=int(year), weeks=len(good),
                                rank_ic_mean=float(ic.mean()) if len(ic) else np.nan,
                                rank_ic_positive_share=float((ic > 0).mean()) if len(ic) else np.nan,
                                net_return=float((1 + good.net_return).prod() - 1) if len(good) else np.nan,
                                turnover_mean=float(good.one_way_turnover.mean()) if len(good) else np.nan))
    yearly = pd.DataFrame(yearly_rows)
    yearly.to_csv(output_dir / 'yearly_evaluation.csv', index=False)
    overall = pd.DataFrame(evaluation_rows)
    overall.to_csv(output_dir / 'evaluation_summary.csv', index=False)
    (output_dir / 'run_config.json').write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding='utf-8')
    write_model_report(output_dir, run_label)



def write_model_report(output_dir: Path, run_label: str) -> None:
    overall = pd.read_csv(output_dir / 'evaluation_summary.csv')
    yearly = pd.read_csv(output_dir / 'yearly_evaluation.csv')
    importance = pd.read_csv(output_dir / 'feature_importance_stability.csv')
    config = json.loads((output_dir / 'run_config.json').read_text(encoding='utf-8'))
    feature_policy = '全部 344 个可用因子' if 'all_usable' in overall.model_id.iloc[0] else '各训练折质量筛选后的因子'
    target_label = {'raw': '原始周收益', 'relative': '截面相对收益',
                    'clipped_relative': '去极值后的截面相对收益'}[config.get('label_mode', 'raw')]
    lines = [f'# LightGBM 因子聚合：{run_label}', '',
             f'本次使用{target_label}作为训练标签、{feature_policy}。参数和训练轮数只使用验证期选择；以下指标来自按年份推进的外层测试期。2026 年为截至数据末日的部分年度。',
             '', '## 外层测试汇总', '',
             '| 模型 | 测试周数 | Rank IC | Rank ICIR | 正 IC 比例 | 成本后年化收益 | 年化波动 | 最大回撤 | 单边换手 |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for _, row in overall.iterrows():
        objective = 'Huber 回归' if '_huber_' in row.model_id else 'LambdaRank 排序'
        lines.append(f'| {objective} | {int(row.weeks)} | {row.rank_ic_mean:.4f} | '
                     f'{row.rank_icir:.3f} | {row.rank_ic_positive_share:.1%} | '
                     f'{row.net_annual_return:.1%} | {row.net_annual_vol:.1%} | '
                     f'{row.net_max_drawdown:.1%} | {row.turnover_mean:.1%} |')
    lines += ['', '## 分年稳定性', '',
              '| 模型 | 测试年 | 周数 | Rank IC | 正 IC 比例 | 成本后累计收益 | 单边换手 |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for _, row in yearly.iterrows():
        objective = 'Huber 回归' if '_huber_' in row.model_id else 'LambdaRank 排序'
        lines.append(f'| {objective} | {int(row.test_year)} | {int(row.weeks)} | '
                     f'{row.rank_ic_mean:.4f} | {row.rank_ic_positive_share:.1%} | '
                     f'{row.net_return:.1%} | {row.turnover_mean:.1%} |')
    lines += ['', '## 跨折重要性（各折 gain 占比）', '',
              '| 目标 | 因子 | 平均 gain 占比 | 覆盖折数 |', '|---|---|---:|---:|']
    for objective, group in importance.groupby('objective'):
        for _, row in group.nlargest(10, 'gain_share_mean').iterrows():
            lines.append(f'| {objective} | {row.factor} | {row.gain_share_mean:.1%} | {int(row.folds)} |')
    lines += ['', '## 结论', '',
              '本次目标函数和分年表现以上表实际输出为准；单次研究结果不代表稳定的未来预测能力。外层测试结果仅用于评价，不反过来选择因子、目标函数或超参数。',
              '', '## 解释与限制', '',
              '- Huber 与 LambdaRank 的原始预测值量纲不同；比较使用逐周截面 Rank IC 和相同分组回测。',
              '- 单边换手率为相邻组合权重绝对变化之和的一半；每周成本为该值乘以 20 bp。',
              '- 本报告使用未复权价格；公司行为可能扭曲收益标签。',
              '- 使用当前可观察股票集合回看历史，偏离任务说明的历史成分股要求；这些数值只供开发研究。' if run_label != 'official' else
              '- 本报告使用传入的历史成分股快照，逐周按当时有效股票池评价。',
              '- 不依据外层测试指标重新选择目标函数、因子或超参数。', '']
    (output_dir / 'model_report.md').write_text('\n'.join(lines), encoding='utf-8')
