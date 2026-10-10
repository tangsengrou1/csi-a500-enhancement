from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from a500.factor_evaluation import evaluate_factors
from a500.factor_registry import make_basic_registry


def read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        return pd.read_excel(path)
    raise ValueError(f"不支持的文件格式: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="周频单因子组合评价")
    parser.add_argument("--market", required=True, help="日频行情 CSV/XLSX")
    parser.add_argument("--constituents", help="历史成分股 CSV/XLSX；正式评价必须提供")
    parser.add_argument("--config", default="Code/factor_evaluation_config.json")
    parser.add_argument("--output", default="Result/factor_reports/basic")
    parser.add_argument(
        "--development-universe", action="store_true",
        help="仅用于开发：将每周有行情的股票视为股票池，不得用于正式报告",
    )
    args = parser.parse_args()
    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)
    if args.development_universe:
        config["allow_development_universe"] = True
    market = read_table(args.market)
    constituents = read_table(args.constituents) if args.constituents else None
    result = evaluate_factors(
        market, constituents, make_basic_registry(), config["factors"], config,
    )
    result.save(args.output)
    print(result.summary.to_string(index=False))
    print(f"评价结果已写入: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
