from __future__ import annotations

import argparse
from pathlib import Path

from a500.io import audit_bundle, load_bundle
from a500.pipeline import load_config, run_backtest
from a500.synthetic import make_synthetic_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description="中证 A500 指数增强研究流程")
    parser.add_argument("command", choices=["audit", "backtest", "demo"])
    parser.add_argument("--config", default="Code/config.json")
    args = parser.parse_args()
    cfg = load_config(args.config)
    root = Path(args.config).resolve().parent.parent
    if args.command == "demo":
        bundle = make_synthetic_bundle()
        out = root / cfg["paths"]["demo_result"]
        run_backtest(bundle, cfg, out, label="SYNTHETIC_DEMO_NOT_FOR_REPORTING")
        print(f"演示流程完成: {out}")
        return
    bundle = load_bundle(root / cfg["paths"]["raw"])
    if args.command == "audit":
        report = audit_bundle(bundle)
        out = root / cfg["paths"]["processed"]
        out.mkdir(parents=True, exist_ok=True)
        report.to_csv(out / "data_audit.csv", index=False)
        print(report.to_string(index=False))
    else:
        out = root / cfg["paths"]["official_result"]
        run_backtest(bundle, cfg, out, label="OFFICIAL_WIND_DATA")
        print(f"正式回测完成: {out}")


if __name__ == "__main__":
    main()

