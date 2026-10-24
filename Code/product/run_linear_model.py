"""Run the shared weekly Ridge/Elastic Net/Lasso/OLS factor aggregation pipeline."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import pandas as pd

from a500.linear_model import run_linear_folds
from a500.tree_model import build_panel


def main() -> None:
    parser = argparse.ArgumentParser(description='周频线性因子聚合模型组')
    parser.add_argument('--config', type=Path, default=Path('Code/config/linear_model.json'))
    parser.add_argument('--market', type=Path, default=Path('Data/raw/processed_data.parquet'))
    parser.add_argument('--factor-store', type=Path, default=Path('Data/factor_store'))
    parser.add_argument('--factor-summary', type=Path,
                        default=Path('Result/factor_reports/train_2020_2022/factor_summary.csv'))
    parser.add_argument('--constituents', type=Path, help='正式运行必须提供历史 A500 成分股快照')
    parser.add_argument('--development-universe', action='store_true')
    parser.add_argument('--smoke', action='store_true', help='只用前 12 个因子和首个测试折')
    parser.add_argument('--test-year', type=int, action='append')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--model-dir', type=Path)
    args = parser.parse_args()
    if args.development_universe and args.constituents:
        parser.error('不能同时指定历史成分股和开发股票池')
    if not args.development_universe and args.constituents is None:
        parser.error('正式运行必须传入 --constituents；调试可使用 --development-universe')
    if args.smoke and not args.development_universe:
        parser.error('--smoke 仅能用于开发模式')
    config = json.loads(args.config.read_text(encoding='utf-8'))
    label = 'smoke' if args.smoke else ('development' if args.development_universe else 'official')
    output = args.output or Path('Result/model_reports') / f'linear_{label}'
    model_dir = args.model_dir or Path('models/linear') / label
    panel = build_panel(args.market, args.factor_store, config, args.constituents,
                        args.development_universe, 12 if args.smoke else None)
    quality = pd.read_csv(args.factor_summary) if args.factor_summary.exists() else None
    years = args.test_year or ([config['first_test_year']] if args.smoke else None)
    run_linear_folds(panel, config, output, model_dir, label, quality, years)
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=False)
    source_paths = [Path(__file__), Path(__file__).parent / 'a500/linear_model.py', args.config]
    manifest = {
        'run_time_utc': datetime.now(timezone.utc).isoformat(), 'data_mode': label,
        'market_path': str(args.market.resolve()), 'factor_store_path': str(args.factor_store.resolve()),
        'factor_count': len(panel.feature_names),
        'factor_list_sha256': hashlib.sha256('\n'.join(panel.feature_names).encode()).hexdigest(),
        'code_commit': commit.stdout.strip() if commit.returncode == 0 else None,
        'source_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
        'constituents_path': str(args.constituents.resolve()) if args.constituents else None,
    }
    (output / 'run_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'运行完成：{output.resolve()}')


if __name__ == '__main__':
    main()
