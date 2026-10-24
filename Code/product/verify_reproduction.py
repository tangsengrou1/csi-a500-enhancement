"""Input checks and independent regression checks for the final product workflow."""
import json
import platform
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import numpy as np
import pandas as pd
from paths import DATA, RAW, RESULT, REFERENCE, MODELS


def runtime_version(name):
    try:
        return version(name)
    except PackageNotFoundError:
        return 'not_installed'


def check_inputs(charts=False, retrain=False):
    required = [RAW/'processed_data.parquet', RAW/'a500_constituents_sw2021l1.parquet',
                RAW/'中证A500全收益指数.xlsx', RAW/'中证A500价格指数每日收盘价.xlsx',
                DATA/'predictions/linear_oos.parquet', DATA/'predictions/tree_oos.parquet']
    if retrain:
        required += [DATA/'data_manifest.json', DATA/'factor_store/alpha158_values',
                     DATA/'factor_store/gtja191_values']
    if charts:
        required += [REFERENCE/'final/组合优化与回测报告.md']
        required += [RAW/'其他指数或指增产品'/name for name in [
            '上证综合全收益指数.xlsx', '沪深300.xlsx', '中证500.xlsx',
            '广发.xlsx', '中金.xlsx', '路迈博中证.xlsx', '天弘.xlsx', '易方达.xlsx']]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError('Missing local product inputs. Set A500_PRODUCT_DATA; see docs/PRODUCT_PIPELINE.md:\n'+'\n'.join(missing))


def verify(compare_reference=True):
    report = {'sources': {}, 'reference_comparison_requested': compare_reference,
              'runtime': {'python': platform.python_version(), 'dependencies': {name: runtime_version(name) for name in ['numpy','pandas','scipy','cvxpy','osqp']}}}
    for model, (folder, suffix) in MODELS.items():
        path = RESULT/folder/f'backtest_weekly_{suffix}.csv'
        frame = pd.read_csv(path)
        if frame.empty or frame.week.duplicated().any():
            raise ValueError(f'Empty or duplicate evaluation blocks: {path}')
        cols = frame.filter(regex=r'^(r_|turn_)').columns
        if not np.isfinite(frame[cols].to_numpy()).all():
            raise ValueError(f'Nonfinite returns or turnover: {path}')
        for key in ['bl', 'blrisk', 'mv', 'eq', 'ind', 'blc']:
            expected = .8*frame.r_idx + .2*(frame[f'r_{key}']-.0015*frame[f'turn_{key}']) - (1.005**(1/52)-1)
            if not np.allclose(expected, frame[f'r_prod_net_{key}'], atol=1e-10, rtol=1e-10):
                raise ValueError(f'Product fee mismatch: {model}/{key}')
        item = {'blocks': len(frame), 'product_fee_check': True}
        reference = REFERENCE/folder/f'backtest_weekly_{suffix}.csv'
        if compare_reference:
            old = pd.read_csv(reference)
            if not frame[['week','w_date','end_date']].equals(old[['week','w_date','end_date']]):
                raise ValueError(f'Reference evaluation window mismatch: {model}')
            errors = (frame[cols]-old[cols]).abs().max()
            item['reference_max_absolute_error'] = float(errors.max())
            item['reference_max_return_error'] = float(errors.filter(regex='^r_').max())
            item['reference_max_turnover_error'] = float(errors.filter(regex='^turn_').max())
            # Old snapshots used different solver versions. Report drift explicitly.
            item['reference_within_tolerance'] = bool(np.allclose(frame[cols], old[cols], atol=1e-6, rtol=1e-5))
        report['sources'][model] = item
    checks = json.loads((RESULT/'final_fusion/validation_results.json').read_text())
    if not checks or not all(value is True for value in checks.values()):
        raise ValueError('Independent holdings/turnover checks did not pass')
    report['independent_holdings_checks'] = checks
    (RESULT/'reproduction_check.json').write_text(json.dumps(report,indent=2)+'\n')
    drift = [name for name,row in report['sources'].items() if row.get('reference_within_tolerance') is False]
    if drift:
        print('WARNING: reference drift for '+', '.join(drift)+'; inspect reproduction_check.json before claiming exact reproduction.')
    print('Product arithmetic and holdings checks passed; '+str(len(report['sources']))+' signal sources checked.')
    return report
