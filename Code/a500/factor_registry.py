from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

import numpy as np
import pandas as pd


FactorCalculator = Callable[["MarketPanel"], pd.DataFrame]


@dataclass(frozen=True)
class MarketPanel:
    """统一的日频因子输入矩阵。行是交易日，列是证券代码。"""

    close: pd.DataFrame
    open: pd.DataFrame | None = None
    high: pd.DataFrame | None = None
    low: pd.DataFrame | None = None
    volume: pd.DataFrame | None = None
    amount: pd.DataFrame | None = None
    vwap: pd.DataFrame | None = None
    turnover: pd.DataFrame | None = None

    def field(self, name: str) -> pd.DataFrame:
        value = getattr(self, name, None)
        if value is None:
            raise ValueError(f"因子需要字段 {name}，但市场数据未提供")
        return value


@dataclass(frozen=True)
class FactorDefinition:
    factor_id: str
    calculator: FactorCalculator
    required_fields: tuple[str, ...] = ("close",)
    direction: int = 1
    library: str = "custom"
    category: str = "unspecified"
    description: str = ""
    source: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.direction not in {-1, 1}:
            raise ValueError("direction 只能为 1 或 -1")


class FactorRegistry:
    """管理内置、开源库适配器和自研因子的统一注册表。"""

    def __init__(self) -> None:
        self._items: dict[str, FactorDefinition] = {}

    def register(self, definition: FactorDefinition) -> None:
        if definition.factor_id in self._items:
            raise ValueError(f"因子已注册: {definition.factor_id}")
        self._items[definition.factor_id] = definition

    def register_library_factor(
        self,
        factor_id: str,
        calculator: FactorCalculator,
        *,
        required_fields: Iterable[str],
        direction: int = 1,
        library: str,
        category: str = "unspecified",
        description: str = "",
        source: str = "",
        metadata: dict | None = None,
    ) -> None:
        """将外部因子库函数包装为统一接口，无需复制评价逻辑。"""
        self.register(FactorDefinition(
            factor_id=factor_id,
            calculator=calculator,
            required_fields=tuple(required_fields),
            direction=direction,
            library=library,
            category=category,
            description=description,
            source=source,
            metadata=metadata or {},
        ))

    def get(self, factor_id: str) -> FactorDefinition:
        if factor_id not in self._items:
            raise KeyError(f"未注册因子: {factor_id}")
        return self._items[factor_id]

    def ids(self) -> list[str]:
        return sorted(self._items)


def _momentum_20(panel: MarketPanel) -> pd.DataFrame:
    return panel.close.pct_change(20, fill_method=None)


def _reversal_5(panel: MarketPanel) -> pd.DataFrame:
    return -panel.close.pct_change(5, fill_method=None)


def _low_volatility_20(panel: MarketPanel) -> pd.DataFrame:
    returns = panel.close.pct_change(fill_method=None)
    return -returns.rolling(20, min_periods=15).std()


def _price_volume_correlation_20(panel: MarketPanel) -> pd.DataFrame:
    returns = panel.close.pct_change(fill_method=None)
    log_volume = np.log1p(panel.field("volume"))
    return returns.rolling(20, min_periods=15).corr(log_volume)


def _turnover_change_20(panel: MarketPanel) -> pd.DataFrame:
    turnover = panel.field("turnover")
    baseline = turnover.rolling(20, min_periods=15).mean().replace(0, np.nan)
    return -(turnover / baseline - 1)


def make_basic_registry() -> FactorRegistry:
    registry = FactorRegistry()
    registry.register(FactorDefinition(
        "momentum_20", _momentum_20, category="momentum",
        description="20个交易日价格动量",
    ))
    registry.register(FactorDefinition(
        "reversal_5", _reversal_5, category="reversal",
        description="过去5个交易日收益的反向值",
    ))
    registry.register(FactorDefinition(
        "low_volatility_20", _low_volatility_20, category="volatility",
        description="过去20个交易日收益波动率的负值",
    ))
    registry.register(FactorDefinition(
        "price_volume_correlation_20", _price_volume_correlation_20,
        required_fields=("close", "volume"), category="price_volume",
        description="收益率与对数成交量的20日滚动相关系数",
    ))
    registry.register(FactorDefinition(
        "turnover_change_20", _turnover_change_20,
        required_fields=("turnover",), category="liquidity",
        description="当日换手率相对20日均值变化的负值",
    ))
    return registry
