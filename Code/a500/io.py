from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


REQUIRED_COLUMNS = {
    "prices": {"date", "wind_code", "close", "adj_close", "amount", "trade_status", "limit_status"},
    "benchmark": {"date", "price_close", "total_return_close"},
    "constituents": {"date", "wind_code", "weight"},
    "industry": {"effective_date", "wind_code", "industry"},
    "valuation": {"date", "wind_code", "pe_ttm", "pb_lf", "ps_ttm", "dividend_yield"},
    "fundamentals": {"announce_date", "report_period", "wind_code", "roe", "gross_margin", "ocf_to_profit", "debt_to_assets"},
    "risk_free": {"date", "annual_rate"},
}


@dataclass
class DataBundle:
    prices: pd.DataFrame
    benchmark: pd.DataFrame
    constituents: pd.DataFrame
    industry: pd.DataFrame
    valuation: pd.DataFrame
    fundamentals: pd.DataFrame
    risk_free: pd.DataFrame


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        return pd.read_excel(path)
    raise ValueError(f"不支持的文件格式: {path}")


def find_table(raw_dir: Path, stem: str) -> Path:
    matches = [p for p in raw_dir.glob(f"{stem}.*") if p.suffix.lower() in {".csv", ".xlsx", ".xlsm"}]
    if len(matches) != 1:
        raise FileNotFoundError(f"{stem} 应恰好有一个 CSV/XLSX 文件，当前找到 {len(matches)} 个")
    return matches[0]


def _parse_dates(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col in out:
            out[col] = pd.to_datetime(out[col], errors="raise").dt.normalize()
    return out


def load_bundle(raw_dir: str | Path) -> DataBundle:
    raw = Path(raw_dir)
    tables = {}
    for name, expected in REQUIRED_COLUMNS.items():
        df = read_table(find_table(raw, name))
        df.columns = [str(c).strip().lower() for c in df.columns]
        missing = expected - set(df.columns)
        if missing:
            raise ValueError(f"{name} 缺少字段: {sorted(missing)}")
        tables[name] = df
    tables["prices"] = _parse_dates(tables["prices"], ["date"])
    tables["benchmark"] = _parse_dates(tables["benchmark"], ["date"])
    tables["constituents"] = _parse_dates(tables["constituents"], ["date"])
    tables["industry"] = _parse_dates(tables["industry"], ["effective_date"])
    tables["valuation"] = _parse_dates(tables["valuation"], ["date"])
    tables["fundamentals"] = _parse_dates(tables["fundamentals"], ["announce_date", "report_period"])
    tables["risk_free"] = _parse_dates(tables["risk_free"], ["date"])
    return DataBundle(**tables)


def audit_bundle(bundle: DataBundle) -> pd.DataFrame:
    rows = []
    for name in REQUIRED_COLUMNS:
        df = getattr(bundle, name)
        date_col = next(c for c in ["date", "effective_date", "announce_date"] if c in df)
        keys = [date_col] + (["wind_code"] if "wind_code" in df else [])
        rows.append({
            "table": name,
            "rows": len(df),
            "start": df[date_col].min(),
            "end": df[date_col].max(),
            "duplicate_keys": int(df.duplicated(keys).sum()),
            "missing_cells": int(df.isna().sum().sum()),
            "status": "PASS" if len(df) and not df.duplicated(keys).any() else "FAIL",
        })
    weights = bundle.constituents.groupby("date")["weight"].sum()
    bad = weights[(weights - 1.0).abs() > 0.01]
    rows.append({"table": "constituent_weight_sum", "rows": len(weights), "start": weights.index.min(), "end": weights.index.max(), "duplicate_keys": 0, "missing_cells": 0, "status": "PASS" if bad.empty else "FAIL"})
    return pd.DataFrame(rows)

