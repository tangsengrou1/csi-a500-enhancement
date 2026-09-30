from __future__ import annotations

import copy
from pathlib import Path

from a500.io import load_bundle
from a500.pipeline import load_config, run_backtest


ROOT = Path(__file__).resolve().parents[1]
BASE = load_config(ROOT / "Code" / "config.json")
BUNDLE = load_bundle(ROOT / BASE["paths"]["raw"])

experiments = []
for cost in (10, 20, 30):
    experiments.append((f"cost_{cost}bp", {"transaction_cost_bps": cost}))
for te in (0.04, 0.05, 0.06):
    experiments.append((f"te_{int(te*100)}pct", {"tracking_error_limit": te}))
experiments.append(("without_black_litterman", {"use_black_litterman": False}))
for factor in ("value", "quality", "momentum", "low_vol"):
    experiments.append((f"exclude_{factor}", {"active_factors": [x for x in BASE["active_factors"] if x != factor]}))

for name, overrides in experiments:
    cfg = copy.deepcopy(BASE)
    cfg.update(overrides)
    run_backtest(BUNDLE, cfg, ROOT / "Result" / "official" / "robustness" / name, label=name)
    print(f"完成: {name}")
