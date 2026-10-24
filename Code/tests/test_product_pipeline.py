"""Regression guards for the final-package prediction and runner integration."""
import importlib.util
from pathlib import Path
import sys
import types
import numpy as np
import pandas as pd
import pytest

PRODUCT = Path(__file__).resolve().parents[1]/'product'


def load_product(name, monkeypatch, tmp_path):
    paths = types.ModuleType('paths')
    for key, value in {'CODE': PRODUCT, 'DATA': tmp_path/'Data', 'RAW': tmp_path/'Data/raw',
                       'RESULT': tmp_path/'Result', 'REFERENCE': tmp_path/'reference',
                       'MODELS': {'linear': ('final','external'), 'tree': ('final_tree','tree'),
                                  'fusion': ('final_fusion','fusion')}}.items():
        setattr(paths, key, value)
    monkeypatch.setitem(sys.modules, 'paths', paths)
    spec = importlib.util.spec_from_file_location('product_test_'+name, PRODUCT/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, paths


def predictions(path, ranks, model='ridge'):
    frame = pd.DataFrame({'signal_date': [pd.Timestamp('2024-01-05')]*2,
                          'wind_code': ['A','B'], 'prediction_rank': ranks,
                          'model_name': model, 'model_id': model+'_version'})
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return frame


def test_product_blend_uses_new_linear_predictions_without_reranking(monkeypatch, tmp_path):
    signals, paths = load_product('signals', monkeypatch, tmp_path)
    paths.RAW.mkdir(parents=True)
    pd.DataFrame({'trade_dt':pd.bdate_range('2024-01-01',periods=20)}).to_parquet(paths.RAW/'processed_data.parquet')
    predictions(paths.DATA/'predictions/linear_oos.parquet',[0,1])
    predictions(paths.DATA/'predictions/tree_oos.parquet',[.4,.6], 'lightgbm_huber')
    new = tmp_path/'retrained.parquet'
    frame = predictions(new,[.2,.8])
    extra = frame.assign(model_name='lasso', model_id='lasso_version', prediction_rank=[1,0])
    pd.concat([frame,extra]).to_parquet(new,index=False)
    signals.prepare(linear_predictions=new)
    out = pd.read_parquet(paths.RESULT/'final_fusion/predictions_fusion.parquet')
    assert np.allclose(out.stacking,[.3,.7])


def test_alignment_rejects_duplicate_model_rows_and_unknown_dates(monkeypatch, tmp_path):
    signals, _ = load_product('signals', monkeypatch, tmp_path)
    path=tmp_path/'pred.parquet'
    frame=predictions(path,[.2,.8])
    pd.concat([frame,frame]).to_parquet(path,index=False)
    with pytest.raises(ValueError,match='Duplicate'):
        signals.align_predictions(path,pd.bdate_range('2024-01-01',periods=20),'ridge')
    frame.assign(signal_date=pd.Timestamp('2027-01-01')).to_parquet(path,index=False)
    with pytest.raises(ValueError,match='日历'):
        signals.align_predictions(path,pd.bdate_range('2024-01-01',periods=20),'ridge')


def test_linear_retraining_uses_development_universe_and_returns_new_output(monkeypatch,tmp_path):
    run, paths=load_product('run',monkeypatch,tmp_path)
    captured=[]
    trainer=types.ModuleType('run_linear_model')
    trainer.main=lambda:captured.extend(sys.argv)
    monkeypatch.setitem(sys.modules,'run_linear_model',trainer)
    original=sys.argv
    result=run.train_linear()
    assert '--development-universe' in captured and '--constituents' not in captured
    assert result==paths.RESULT/'linear_training/oos_predictions.parquet'
    assert sys.argv is original


def test_preflight_explains_missing_local_data(monkeypatch,tmp_path):
    verifier,_=load_product('verify_reproduction',monkeypatch,tmp_path)
    with pytest.raises(FileNotFoundError,match='A500_PRODUCT_DATA'):
        verifier.check_inputs()


def test_verifier_rejects_incorrect_product_fee(monkeypatch,tmp_path):
    verifier,paths=load_product('verify_reproduction',monkeypatch,tmp_path)
    folder=paths.RESULT/'final'
    folder.mkdir(parents=True)
    data={'week':[1], 'w_date':['2024-01-01'], 'end_date':['2024-01-08'], 'r_idx':[.01]}
    for key in ['bl','blrisk','mv','eq','ind','blc']:
        data[f'r_{key}']=[.02]
        data[f'turn_{key}']=[.5]
        data[f'r_prod_net_{key}']=[.99]
    pd.DataFrame(data).to_csv(folder/'backtest_weekly_external.csv',index=False)
    with pytest.raises(ValueError,match='Product fee mismatch'):
        verifier.verify(compare_reference=False)
