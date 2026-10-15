import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from a500.linear_model import candidate_grid, run_linear_folds, screen_linear_features
from a500.tree_model import FactorPanel


def make_panel(seed=17, n_stocks=24):
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2020-01-03', '2024-12-27', freq='W-FRI')
    codes = pd.Index([f'S{i:03d}' for i in range(n_stocks)])
    rows = len(dates) * n_stocks
    base = rng.normal(size=rows)
    features = np.column_stack([
        base,
        base + rng.normal(scale=.01, size=rows),
        rng.normal(size=rows),
        rng.normal(size=rows),
        rng.normal(size=rows),
    ]).astype(np.float32)
    labels = .02 * base - .015 * features[:, 2] + rng.normal(scale=.01, size=rows)
    samples = pd.DataFrame({
        'signal_date': np.repeat(dates, n_stocks),
        'execution_date': np.repeat(dates + pd.Timedelta(days=3), n_stocks),
        'target_end_date': np.repeat(dates + pd.Timedelta(days=10), n_stocks),
        'wind_code': np.tile(codes, len(dates)),
        'in_universe': True,
        'label': labels,
        'target': labels,
        'entry_price': 1.0,
        'exit_price': 1.0 + labels,
    })
    return FactorPanel(features, ['strong', 'strong_copy', 'negative', 'noise1', 'noise2'],
                       samples, pd.DatetimeIndex(dates), codes)


def config():
    path = Path(__file__).resolve().parents[1] / 'config' / 'linear_model.json'
    cfg = json.loads(path.read_text(encoding='utf-8'))
    cfg.update(minimum_train_coverage=.5, minimum_valid_week_share=.5,
               minimum_ic_weeks=20, minimum_abs_rank_ic=.02,
               maximum_abs_pairwise_correlation=.7, maximum_selected_factors=4,
               minimum_train_weeks=50)
    cfg['ridge_alphas'] = [1.0]
    cfg['elastic_net_alphas'] = [.001]
    cfg['elastic_net_l1_ratios'] = [.5]
    cfg['lasso_alphas'] = [.001]
    return cfg


def test_ic_and_correlation_screen_keeps_signal_but_removes_duplicate():
    panel = make_panel()
    train = panel.samples.signal_date.dt.year.to_numpy() <= 2022
    quality = pd.DataFrame({
        'factor': panel.feature_names,
        'net_sharpe': [2.0, 1.0, 1.5, 0.0, 0.0],
        'net_annual_return': [.2, .1, .15, 0.0, 0.0],
        'rank_ic_positive_share': [.8, .8, .2, .5, .5],
    })
    result = screen_linear_features(panel, train, config(), quality)
    selected = {panel.feature_names[i] for i in result.indices}
    assert 'strong' in selected
    assert 'negative' in selected
    assert not {'strong', 'strong_copy'}.issubset(selected)
    duplicate = result.report[result.report.factor == 'strong_copy'].iloc[0]
    assert duplicate.reason == 'CORRELATION_GATE'


def test_four_model_grids_and_end_to_end_outputs(tmp_path):
    cfg = config()
    assert set(cfg['models']) == {'ridge', 'elastic_net', 'lasso', 'ols'}
    assert candidate_grid('ols', cfg) == [{}]
    output = tmp_path / 'results'
    models = tmp_path / 'models'
    run_linear_folds(make_panel(), cfg, output, models, 'test', test_years=[2024])
    predictions = pd.read_parquet(output / 'oos_predictions.parquet')
    assert set(predictions.model_name) == {'ridge', 'elastic_net', 'lasso', 'ols'}
    assert predictions.groupby('model_name').fold_id.nunique().eq(1).all()
    for name in ['feature_screen.csv', 'validation_candidates.csv', 'fold_models.csv',
                 'factor_coefficients.csv', 'coefficient_stability.csv',
                 'weekly_evaluation.csv', 'yearly_evaluation.csv',
                 'evaluation_summary.csv', 'model_report.md']:
        assert (output / name).exists()
