"""Warehouse digital twin: the physical scenario in which SAMG is demonstrated (owner: Dev B).

The warehouse layer translates orders into SAMG missions and SAMG decisions into robot
motion. Topology selection, allocation, execution, witness, ACP and learning are SAMG's.
"""

from samg.twin.adapter import (
    WarehouseEnv,
    WarehouseRun,
    build_state,
    compare_policies,
    run_warehouse,
)
from samg.twin.layout import Layout, load_config
from samg.twin.scenarios import INJECTION_KINDS, POLICY_KINDS, Injection, RunSpec, preset

__all__ = [
    "INJECTION_KINDS",
    "POLICY_KINDS",
    "Injection",
    "Layout",
    "RunSpec",
    "WarehouseEnv",
    "WarehouseRun",
    "build_state",
    "compare_policies",
    "load_config",
    "preset",
    "run_warehouse",
]
