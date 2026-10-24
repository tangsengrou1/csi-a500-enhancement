"""将模型预测映射到原研究的5交易日周，合并同周同股票分数。"""
import json
import numpy as np
import pandas as pd
from paths import DATA, RAW, RESULT, MODELS


def align_predictions(path, calendar, model_name=None):
    frame = pd.read_parquet(path).sort_values('signal_date')
    if model_name is not None and 'model_name' in frame:
        frame = frame.loc[frame.model_name.eq(model_name)].copy()
    if frame.empty:
        raise ValueError(f'No predictions for {model_name}: {path}')
    if frame.duplicated(['signal_date', 'wind_code']).any():
        raise ValueError('Duplicate signal/stock keys; select one model before alignment')
    if 'model_id' in frame and frame.model_id.nunique() != 1:
        raise ValueError('Multiple model versions in one prediction source')
    signal = pd.DatetimeIndex(pd.to_datetime(frame.signal_date))
    index = calendar.searchsorted(signal)
    if (index >= len(calendar)).any() or not (calendar[index] == signal).all():
        raise ValueError('信号日期不在行情日历中')
    frame['pred_week'] = index // 5 + 2
    frame = frame.drop_duplicates(['pred_week', 'wind_code'], keep='last')
    frame = frame.rename(columns={'signal_date':'feature_dt', 'wind_code':'securityID', 'prediction_rank':'stacking'})
    frame = frame[['pred_week','feature_dt','securityID','stacking']]
    assert frame.stacking.notna().all() and frame.stacking.between(0,1).all()
    cutoff = (frame.pred_week.to_numpy()-1)*5-1
    if (cutoff >= len(calendar)).any():
        raise ValueError('行情不足以覆盖预测的组合信息截止日')
    if not (pd.to_datetime(frame.feature_dt).to_numpy() <= calendar[cutoff].to_numpy()).all():
        raise ValueError('信号晚于组合信息截止日')
    return frame.sort_values(['pred_week','securityID']).reset_index(drop=True)


def prepare(tree_predictions=None, linear_predictions=None):
    calendar = pd.DatetimeIndex(sorted(pd.to_datetime(pd.read_parquet(RAW/'processed_data.parquet', columns=['trade_dt']).trade_dt.unique())))
    linear = align_predictions(linear_predictions or DATA/'predictions/linear_oos.parquet', calendar, 'ridge')
    tree = align_predictions(tree_predictions or DATA/'predictions/tree_oos.parquet', calendar, 'lightgbm_huber')
    keys = ['pred_week','securityID']
    merged = linear.merge(tree, on=keys, how='outer', suffixes=('_linear','_tree'), validate='one_to_one', indicator=True)
    if not merged._merge.eq('both').all():
        raise ValueError('覆盖范围不一致，不允许静默丢弃')
    if not merged.feature_dt_linear.equals(merged.feature_dt_tree):
        raise ValueError('两侧信号日期不同')
    merged['feature_dt'] = merged.feature_dt_linear
    # 两个截面百分位直接算术平均，不对平均值重新排名。
    merged['stacking'] = .5*merged.stacking_linear + .5*merged.stacking_tree
    fusion = merged[keys+['feature_dt','stacking']]
    for model, frame in [('linear',linear),('tree',tree),('fusion',fusion)]:
        folder, suffix = MODELS[model]
        out = RESULT/folder
        out.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(out/f'predictions_{suffix}.parquet', index=False)
    merged[keys+['feature_dt','stacking_linear','stacking_tree','stacking']].to_parquet(RESULT/'final_fusion/fusion_signal_audit.parquet',index=False)
    manifest = dict(linear_weight=.5,tree_weight=.5,rerank_after_fusion=False,weeks=int(fusion.pred_week.nunique()),rows=len(fusion),securities=int(fusion.securityID.nunique()),signal_cutoff_check=True)
    (RESULT/'final_fusion/run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
