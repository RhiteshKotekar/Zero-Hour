# Test layout

- `unit/` tests a module with controlled fixtures and no database or Streamlit runtime.
- `contract/` locks down cross-team Pydantic payloads, enum values, and public interface behaviour.
- `integration/` runs the mission path from topology decision through persistence.

Tests must seed all random generators explicitly. Optimisation tests should assert feasibility and objective relationships rather than relying on arbitrary solver tie-breaking.
