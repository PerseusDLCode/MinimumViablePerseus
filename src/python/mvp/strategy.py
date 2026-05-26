# mvp/strategy.py — shim; removed in cleanup commit
from mvp.site.strategy import *  # noqa: F401,F403
from mvp.site.strategy import (
    ChunkingStrategy, MilestoneStrategy, DivisionStrategy, StrategySelector,
)
