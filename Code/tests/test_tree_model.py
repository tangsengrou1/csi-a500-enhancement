import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from a500.tree_model import (FactorPanel, cross_section_rank, evaluate_predictions,
                             make_training_target,
                             ranking_relevance, screen_features, split_fold, weekly_schedule)


def test_weekly_schedule_and_rank_do_not_use_future_rows():
    dates = pd.bdate_range('2023-12-25', '2024-01-15')
    periods = weekly_schedule(dates)
    assert periods[0] == (pd.Timestamp('2023-12-29'), pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-08'))
    values = pd.DataFrame([[1, 2, 2, np.inf], [900, 0, 0, 0]], index=[0, 1])
    ranked = cross_section_rank(values, 0, 1)
    assert np.isclose(ranked.iloc[0, 0], 0)
    assert np.isclose(ranked.iloc[0, 1], .75)
    assert np.isnan(ranked.iloc[0, 3])
    assert np.isclose(ranked.iloc[1, 0], 1)


def test_fold_purges_labels_that_cross_boundaries():
    frame = pd.DataFrame({
        'signal_date':pd.to_datetime(['2022-12-23','2022-12-30','2023-01-06',
                                      '2023-12-22','2023-12-29','2024-01-05']),
        'target_end_date':pd.to_datetime(['2022-12-30','2023-01-09','2023-01-13',
                                          '2023-12-29','2024-01-08','2024-01-12']),
        'in_universe':[True]*6, 'label':[.01]*6,
    })
    masks=split_fold(frame, 2024)
    assert masks['train'].tolist() == [True,False,False,False,False,False]
    assert masks['validation'].tolist() == [False,False,True,True,False,False]
    assert masks['test'].tolist() == [False,False,False,False,False,True]


def test_quality_screen_uses_only_train_rows():
    dates=pd.to_datetime(['2020-01-03']*3+['2020-01-10']*3+['2024-01-05']*3)
    sample=pd.DataFrame({'signal_date':dates})
    x=np.array([[1,np.nan],[2,np.nan],[3,np.nan],
                [1,np.nan],[2,np.nan],[3,np.nan],
                [1,1],[2,2],[3,3]],dtype=np.float32)
    panel=FactorPanel(x,['good','future_only'],sample,pd.DatetimeIndex(dates.unique()),pd.Index(list('abc')))
    config={'feature_policy':'quality_screen','minimum_train_coverage':.8,'minimum_valid_week_share':.9}
    selected,status=screen_features(panel,np.array([True]*6+[False]*3),config)
    assert selected==[0]
    assert status.loc[status.factor=='future_only','reason'].iloc[0]=='NO_VARIATION'


def test_ranking_groups_and_one_way_cost():
    relevance,group=ranking_relevance(np.array([.1,.2,.3,.4,.5,.6]),
                                       np.array([1,1,1,2,2,2]))
    assert group==[3,3]
    assert np.all(np.diff(relevance[:3])>=0)
    rows=[]
    for signal in pd.to_datetime(['2024-01-05','2024-01-12']):
        for i in range(20):
            rows.append(dict(signal_date=signal,wind_code=f'S{i}',prediction=float(i),
                             in_universe=True,entry_price=100.,label=.01 if i>=16 else -.01))
    weekly,summary=evaluate_predictions(pd.DataFrame(rows),minimum_stocks=20,
                                         cost_bps_one_way=20,tail_fraction=.2)
    assert weekly.status.tolist()==['OK','OK']
    assert np.isclose(weekly.one_way_turnover.iloc[0],.5)
    assert np.isclose(weekly.cost.iloc[0],.001)
    assert np.isclose(weekly.one_way_turnover.iloc[1],0)
    assert summary['weeks']==2


def test_training_targets_are_week_local_and_do_not_change_raw_returns():
    raw = np.array([[.01, .02, .50, np.nan], [-.03, .01, .02, np.nan]])
    original = raw.copy()
    relative = make_training_target(raw, 'relative')
    clipped = make_training_target(raw, 'clipped_relative')
    assert np.allclose(np.nanmean(relative, axis=1), 0)
    assert np.allclose(np.nanmean(clipped, axis=1), 0)
    assert clipped[0, 2] < relative[0, 2]
    assert np.array_equal(raw, original, equal_nan=True)
