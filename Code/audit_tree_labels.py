"""Audit raw weekly return labels and adjusted-price overlap without changing models."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from a500.tree_model import weekly_schedule


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--market', type=Path, default=Path('Data/raw/processed_data.parquet'))
    parser.add_argument('--adjusted', type=Path, default=Path('Data/raw/prices.csv'))
    parser.add_argument('--output', type=Path, default=Path('Result/model_reports/tree_label_audit'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    raw = pd.read_parquet(args.market, columns=['trade_dt', 'securityID', 'close'])
    raw['trade_dt'] = pd.to_datetime(raw.trade_dt).dt.normalize()
    schedule = pd.DataFrame(weekly_schedule(pd.DatetimeIndex(raw.trade_dt.unique())),
                            columns=['signal_date', 'execution_date', 'target_end_date'])
    universe = raw[['securityID', 'trade_dt', 'close']].rename(columns={'trade_dt': 'signal_date'})
    entries = raw.rename(columns={'trade_dt': 'execution_date', 'close': 'entry_price'})
    exits = raw.rename(columns={'trade_dt': 'target_end_date', 'close': 'exit_price'})
    weekly = schedule.merge(universe, on='signal_date', how='left')
    weekly = weekly.merge(entries, on=['securityID', 'execution_date'], how='left')
    weekly = weekly.merge(exits, on=['securityID', 'target_end_date'], how='left')
    weekly['raw_return'] = weekly.exit_price / weekly.entry_price - 1
    weekly.loc[weekly.entry_price.le(0) | weekly.exit_price.le(0), 'raw_return'] = np.nan
    adjusted = pd.read_csv(args.adjusted, usecols=['date', 'wind_code', 'adj_close'])
    adjusted['date'] = pd.to_datetime(adjusted.date).dt.normalize()
    adj_entry = adjusted.rename(columns={'date': 'execution_date', 'wind_code': 'securityID',
                                          'adj_close': 'adj_entry'})
    adj_exit = adjusted.rename(columns={'date': 'target_end_date', 'wind_code': 'securityID',
                                         'adj_close': 'adj_exit'})
    weekly = weekly.merge(adj_entry, on=['securityID', 'execution_date'], how='left')
    weekly = weekly.merge(adj_exit, on=['securityID', 'target_end_date'], how='left')
    weekly['adjusted_return'] = weekly.adj_exit / weekly.adj_entry - 1
    weekly['adjustment_gap'] = weekly.raw_return - weekly.adjusted_return
    weekly['suspected_corporate_action'] = weekly.adjustment_gap.abs() > .05
    extreme = weekly.loc[weekly.raw_return.abs() > .3].copy()
    extreme = extreme.sort_values('raw_return', key=lambda s: s.abs(), ascending=False)
    extreme[['signal_date', 'execution_date', 'target_end_date', 'securityID',
             'raw_return', 'adjusted_return', 'adjustment_gap',
             'suspected_corporate_action']].to_csv(args.output / 'extreme_raw_returns.csv', index=False)
    overlap = weekly.dropna(subset=['raw_return', 'adjusted_return']).copy()
    overlap[['signal_date', 'securityID', 'raw_return', 'adjusted_return',
             'adjustment_gap']].to_parquet(args.output / 'adjusted_overlap_labels.parquet', index=False)
    overlap.loc[overlap.adjustment_gap.abs() > .05,
                ['signal_date', 'execution_date', 'target_end_date', 'securityID',
                 'raw_return', 'adjusted_return', 'adjustment_gap']].sort_values(
                     'adjustment_gap', key=lambda s: s.abs(), ascending=False).to_csv(
                         args.output / 'large_adjustment_gaps.csv', index=False)
    summary = pd.DataFrame([{
        'raw_weekly_labels': int(weekly.raw_return.notna().sum()),
        'extreme_abs_return_over_30pct': len(extreme),
        'adjusted_overlap_labels': len(overlap),
        'overlap_abs_gap_over_5pp': int((overlap.adjustment_gap.abs() > .05).sum()),
        'overlap_raw_vs_adjusted_correlation': overlap.raw_return.corr(overlap.adjusted_return),
        'adjusted_first_date': adjusted.date.min(),
        'adjusted_last_date': adjusted.date.max(),
    }])
    summary.to_csv(args.output / 'summary.csv', index=False)
    print(summary.to_string(index=False))


if __name__ == '__main__':
    main()
