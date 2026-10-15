"""Run the shared weekly LightGBM regression/ranking research pipeline."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from a500.tree_model import build_panel, run_folds


def main() -> None:
    parser = argparse.ArgumentParser(description='周频 LightGBM 因子聚合')
    parser.add_argument('--config', type=Path, default=Path('Code/config/tree_model.json'))
    parser.add_argument('--market', type=Path, default=Path('Data/raw/processed_data.parquet'))
    parser.add_argument('--factor-store', type=Path, default=Path('Data/factor_store'))
    parser.add_argument('--constituents', type=Path, help='正式运行必须提供的历史 A500 成分股快照')
    parser.add_argument('--development-universe', action='store_true',
                        help='仅开发调试：使用文件中有行情的股票，结果不可称为正式回测')
    parser.add_argument('--smoke', action='store_true', help='8 个因子、1 折、少量迭代的管线冒烟测试')
    parser.add_argument('--feature-policy', choices=['quality_screen', 'all_usable'],
                        help='覆盖配置中的因子筛选策略，用于同口径敏感性实验')
    parser.add_argument('--test-year', type=int, action='append', help='只跑指定外层测试年份，可重复传入')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--model-dir', type=Path)
    args = parser.parse_args()
    if args.development_universe and args.constituents:
        parser.error('不能同时指定历史成分股和开发股票池')
    if not args.development_universe and args.constituents is None:
        parser.error('正式运行必须传入 --constituents；调试可显式使用 --development-universe')
    if args.smoke and not args.development_universe:
        parser.error('--smoke 仅能用于开发模式')
    config = json.loads(args.config.read_text(encoding='utf-8'))
    if args.feature_policy:
        config['feature_policy'] = args.feature_policy
    if config['feature_policy'] not in {'quality_screen', 'all_usable'}:
        parser.error('feature_policy 只能为 quality_screen 或 all_usable')
    if args.smoke:
        config['candidates'] = config['candidates'][:1]
        config['num_boost_round'] = 35
        config['early_stopping_rounds'] = 8
    label = 'smoke' if args.smoke else ('development' if args.development_universe else 'official')
    suffix = '' if config['feature_policy'] == 'quality_screen' else '_all_usable'
    output = args.output or Path('Result/model_reports') / f'tree_{label}{suffix}'
    model_dir = args.model_dir or Path('models/tree') / f'{label}{suffix}'
    panel = build_panel(args.market, args.factor_store, config, args.constituents,
                        args.development_universe, 8 if args.smoke else None)
    years = args.test_year or ([config['first_test_year']] if args.smoke else None)
    run_folds(panel, config, output, model_dir, label, years)
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=False)
    source_paths = [Path(__file__), Path(__file__).parent / 'a500/tree_model.py', args.config]
    source_hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}
    manifest = {
        'run_time_utc': datetime.now(timezone.utc).isoformat(),
        'data_mode': label,
        'market_path': str(args.market.resolve()),
        'market_size_bytes': args.market.stat().st_size,
        'factor_store_path': str(args.factor_store.resolve()),
        'factor_count': len(panel.feature_names),
        'factor_list_sha256': hashlib.sha256('\n'.join(panel.feature_names).encode()).hexdigest(),
        'code_commit': commit.stdout.strip() if commit.returncode == 0 else None,
        'source_sha256': source_hashes,
        'random_seed': config['seed'],
        'constituents_path': str(args.constituents.resolve()) if args.constituents else None,
    }
    (output / 'run_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'运行完成：{output.resolve()}')
    if args.development_universe:
        print('开发股票池可能包含幸存者偏差；结果不是正式 A500 样本外结论。')


if __name__ == '__main__':
    main()
