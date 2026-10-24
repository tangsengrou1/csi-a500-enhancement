"""提交包唯一运行入口。默认使用归档预测，重算三套信号×六组合。"""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import importlib
import json
import hashlib
import platform
import shutil
import sys
from pathlib import Path
from paths import CODE, DATA, RAW, RESULT, REFERENCE, MODELS


def optimize(model):
    """同一组优化实现接收不同预测，不跨模型复用历史权重。"""
    folder, suffix = MODELS[model]
    out = RESULT/folder
    for name, version in [('portfolio_basic',1),('portfolio_mv',2),('portfolio_bl',3)]:
        module = importlib.import_module(name)
        module.PRED_PARQUET = out/f'predictions_{suffix}.parquet'
        module.OUT_PARQUET = out/f'portfolio_weights_v{version}_{suffix}.parquet'
        module.OUT_INDDEV = out/f'industry_deviation_v{version}_{suffix}.parquet'
        # 原单模型使用OSQP默认精度，融合沿用定稿时的严格精度。
        module.SOLVER_OPTIONS = dict(eps_abs=1e-9,eps_rel=1e-9,max_iter=100000,polishing=True) if model=='fusion' else {}
        with (out/f'{name}.log').open('w',encoding='utf-8') as log, redirect_stdout(log), redirect_stderr(log):
            module.main()
    import backtest
    backtest.ROOT = out
    backtest.WEIGHTS_PARQUET = out/f'portfolio_weights_v1_{suffix}.parquet'
    backtest.WEIGHTS_V2_PARQUET = out/f'portfolio_weights_v2_{suffix}.parquet'
    backtest.WEIGHTS_V3_PARQUET = out/f'portfolio_weights_v3_{suffix}.parquet'
    # 回测内部统一临时后缀，结束后改成各模型后缀。
    with (out/'backtest.log').open('w',encoding='utf-8') as log, redirect_stdout(log), redirect_stderr(log):
        backtest.main()
    for path in list(out.glob('*_fusion.*')):
        if suffix!='fusion': path.replace(path.with_name(path.name.replace('_fusion.',f'_{suffix}.')))


def train_tree():
    from feature_engineering import build_panel
    from tree_model import run_folds
    config = json.loads((CODE/'config/tree_model.json').read_text(encoding='utf-8'))
    out = RESULT/'tree_training'
    out.mkdir(parents=True,exist_ok=True)
    with (out/'training.log').open('w',encoding='utf-8') as log, redirect_stdout(log), redirect_stderr(log):
        panel = build_panel(RAW/'processed_data.parquet',DATA/'factor_store',config,development_universe=True)
        run_folds(panel,config,out,out/'models','development')
    write_training_manifest(out)
    return out/'oos_predictions.parquet'


def train_linear():
    """Run the restored Ridge/linear-model source on the package inputs."""
    import run_linear_model

    old_argv = sys.argv
    try:
        sys.argv = [
            'run_linear_model.py',
            '--config', str(CODE/'config/linear_model.json'),
            '--market', str(RAW/'processed_data.parquet'),
            '--factor-store', str(DATA/'factor_store'),
            '--development-universe',
            '--factor-summary', str(Path(__file__).resolve().parents[2]/'Result/factor_reports/train_2020_2022/factor_summary.csv'),
            '--output', str(RESULT/'linear_training'),
            '--model-dir', str(RESULT/'linear_training'/'models'),
        ]
        run_linear_model.main()
    finally:
        sys.argv = old_argv
    return RESULT/'linear_training/oos_predictions.parquet'


def write_training_manifest(out):
    """记录实际提交代码和输入清单；不把原机器绝对路径作为依赖。"""
    from importlib.metadata import version
    names=['feature_engineering.py','factor_screening.py','tree_model.py','config/tree_model.json']
    manifest={
        'python':platform.python_version(),
        'dependencies':{name:version(name) for name in ['numpy','pandas','lightgbm','pyarrow']},
        'source_sha256':{name:hashlib.sha256((CODE/name).read_bytes()).hexdigest() for name in names},
        'input_manifest_sha256':hashlib.sha256((DATA/'data_manifest.json').read_bytes()).hexdigest(),
        'data_mode':'development',
        'factor_input':'Data/factor_store',
        'market_input':'Data/raw/processed_data.parquet',
        'linear_retraining_available':True,
    }
    (out/'run_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')


def render():
    import evaluation
    import visualization
    fusion = RESULT/'final_fusion'
    evaluation.ROOT, evaluation.BASE = fusion, RESULT
    with (fusion/'evaluation.log').open('w',encoding='utf-8') as log, redirect_stdout(log), redirect_stderr(log):
        evaluation.main()
    # 报告只读取此包内冻结的方法说明；不把原目录当作运行依赖。
    shutil.copy2(REFERENCE/'final/组合优化与回测报告.md',RESULT/'final/组合优化与回测报告.md')
    visualization.ROOT, visualization.BASE = fusion, RESULT
    with (fusion/'visualization.log').open('w',encoding='utf-8') as log, redirect_stdout(log), redirect_stderr(log):
        visualization.main()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-inputs', action='store_true', help='仅检查本地输入是否齐备')
    parser.add_argument('--skip-charts', action='store_true', help='运行优化、回测和评价，跳过全套图表')
    parser.add_argument('--train-tree', action='store_true',help='先从包内因子重训完整LightGBM，再执行优化与回测')
    parser.add_argument('--train-linear', action='store_true',help='从包内因子和行情重训Ridge/线性模型')
    parser.add_argument('--charts-only', action='store_true',help='使用已经重算的周收益重绘融合22张图')
    args=parser.parse_args()
    from verify_reproduction import check_inputs
    if args.check_inputs:
        check_inputs(charts=True, retrain=args.train_tree or args.train_linear)
        print('本地输入检查通过')
        return
    if not args.charts_only:
        check_inputs(charts=not args.skip_charts, retrain=args.train_tree or args.train_linear)
    RESULT.mkdir(parents=True,exist_ok=True)
    linear = train_linear() if args.train_linear else None
    if not args.charts_only:
        tree = train_tree() if args.train_tree else None
        from signals import prepare
        prepare(tree, linear)
        for model in MODELS:
            print(f'重新优化及回测：{model}',flush=True)
            optimize(model)
    print('生成图表与报告',flush=True)
    if args.skip_charts:
        import evaluation
        evaluation.ROOT, evaluation.BASE = RESULT/'final_fusion', RESULT
        evaluation.main()
    else:
        render()
    from verify_reproduction import verify
    verify(compare_reference=not (args.train_tree or args.train_linear))
    print(f'完成：{RESULT}',flush=True)


if __name__=='__main__':
    main()
