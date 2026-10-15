import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_factor_quality_report import rank_weights, metrics


def test_rank_weights_are_dollar_neutral_and_extreme_weighted():
    ranks, longs, shorts = rank_weights(pd.Series([1, 2, 3, 4, 5], index=list('abcde')))
    assert ranks.to_dict() == dict(zip('abcde', [0, .25, .5, .75, 1]))
    assert np.isclose(longs.sum(), .5)
    assert np.isclose(shorts.sum(), -.5)
    assert np.isclose(longs.loc['c'] + shorts.loc['c'], 0)
    assert longs.loc['e'] > longs.loc['d']
    assert abs(shorts.loc['a']) > abs(shorts.loc['b'])


def test_rank_weights_do_not_invent_two_sided_portfolio():
    for values in ([1, 1, 1], [np.nan, 2, 2]):
        ranks, longs, shorts = rank_weights(pd.Series(values))
        assert ranks.empty and longs.empty and shorts.empty


def test_risk_metrics_from_unsmoothed_weekly_returns():
    returns = pd.Series([.10, -.20, .05])
    result = metrics(returns)
    assert result['weeks'] == 3
    assert np.isclose(result['cumulative_return'], 1.1 * .8 * 1.05 - 1)
    assert np.isclose(result['var_5'], returns.quantile(.05))
    assert np.isclose(result['cvar_5'], -.2)
