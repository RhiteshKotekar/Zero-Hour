# Test layout

- `unit/` tests a module with controlled fixtures and no database or Streamlit runtime.
- `contract/` locks down cross-team Pydantic payloads, enum values, and public interface behaviour.
- `integration/` runs the mission path from topology decision through persistence.

Tests must seed all random generators explicitly. Optimisation tests should assert feasibility and objective relationships rather than relying on arbitrary solver tie-breaking.

## Neural allocator baseline tests (deferred; D022–D029)

These apply only if the optional, post-hackathon `samg.nco` baseline is added. The MVP suite has no neural tests and does not need PyTorch.

- Run on **CPU** with the CPU torch build in the project venv, using `torch.manual_seed`, a seeded `torch.Generator` and `torch.use_deterministic_algorithms(True)`. Tests never require XPU, the NPU, PyTorch Geometric or a trained checkpoint.
- Mask tests compare `nco/env.py` with `contract/fixtures/nco_masks_judge.json`, an oracle derived independently from the CP-SAT constraint set.
- A Hypothesis property test checks random masked rollouts on generated instances. Each rollout must end either in a plan accepted by `allocation.validate_plan` or in an explicit dead end.
- Security tests: a checkpoint with a flipped byte or no `FROZEN` row is refused (INV-11); a static import check shows that `samg.nco` does not import `persistence`, `assurance` or witness code (INV-10); an invalid neural plan triggers the CP-SAT/greedy fallback with a reason code (INV-12).
- Training smoke tests run a few Pa-POMO steps on tiny instances and are marked `slow`. Real training runs outside `pytest`, in the separate XPU venv. See [PAPER_ALIGNMENT.md](../docs/PAPER_ALIGNMENT.md) §6.
