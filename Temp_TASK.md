# CONTINUATION TASK: SAMG Validator — Claude Opus 4.6 Handoff

You are taking over an existing development and validation task from Claude Opus 4.6.

This is NOT a fresh implementation task.

Claude Opus has already worked on the project, and you must continue from its actual repository state rather than restarting or reimplementing completed work.

You are acting as the Validator (V) for SAMG — Secure Adaptive Mission Graphs.

## 1. FIRST: Recover the previous assistant's work

Before doing anything, inspect:

1. `CLAUDE.md`
2. `docs/THREE_PERSON_PLAN.md`
3. `docs/VALIDATOR_HANDOFF.md`
4. `docs/VALIDATION_LOG.md`
5. `docs/DECISIONS.md`
6. `docs/WORK_QUEUE.md`

Also inspect the relevant implementation and test files mentioned in the handoff.

IMPORTANT:

- `VALIDATOR_HANDOFF.md` is your primary continuation document.
- `VALIDATION_LOG.md` contains the official validation evidence.
- Git history and the actual source code are authoritative for determining what was implemented.
- Do not assume every task described as completed in documentation is actually working.
- Do not assume Opus finished its last operation successfully.

Reconcile all three: documentation, Git state and implementation.

## 2. Establish the exact current state

Run and inspect:

```bash
git status
git branch --show-current
git rev-parse HEAD
git log -10 --oneline
```

Identify:

- Files modified by Claude.
- Uncommitted changes.
- New files.
- Tests added.
- Tests actually executed.
- Tests that failed.
- Tasks left incomplete.
- Any partially implemented functionality.

Do not discard, reset, overwrite or clean existing changes.

Do not commit or push unless explicitly instructed.

## 3. Understand the original JSON issue

The immediate priority was fixing the experiment JSON serialization/deserialization mismatch between:

- `scripts/run_experiment_a.py`
- `src/samg/dashboard/data.py`
- `ExperimentResult`
- `summary_json(result)`
- The Adaptive Evaluation Lab dashboard.

The original issue was that a summary-only JSON artifact was being loaded as though it contained a complete `ExperimentResult`.

The intended solution was to maintain a clear separation between:

1. A complete machine-readable experiment artifact.
2. A human-readable summary artifact.

Inspect what Opus actually implemented.

Verify:

- Full artifact serialization.
- Full artifact deserialization.
- Summary artifact generation.
- Dashboard data loading.
- Backward compatibility.
- Missing and malformed artifact handling.
- Legacy summary-only JSON handling.

Do not reimplement this if Opus already fixed it correctly.

If it is incomplete or incorrect, finish the existing implementation with minimal changes.

## 4. Verify the JSON fix independently

Do not rely solely on Opus's reported test results.

Run the relevant tests yourself.

Then execute the real workflow:

1. Generate Experiment A using the existing runner.
2. Confirm the expected JSON artifacts are created.
3. Deserialize the full artifact into `ExperimentResult`.
4. Launch the Streamlit dashboard.
5. Verify the Adaptive Evaluation Lab loads the experiment.
6. Verify the policy comparison data.
7. Verify the learning curves.
8. Verify missing and malformed artifact handling.

If actual browser interaction is unavailable, use Streamlit AppTest or suitable automated checks and explicitly state the limitation.

Do not fabricate results.

## 5. Continue the Validator plan

After verifying the JSON integration fix, continue from the first incomplete task in `VALIDATOR_HANDOFF.md`.

Follow the original ownership boundaries in `docs/THREE_PERSON_PLAN.md`.

Your permitted work includes:

- Independent validation.
- Contract fixture data.
- Validation documentation.
- Experiment result verification.
- Demo scripts.
- Dashboard JSON integration.
- Relevant tests.

Do not rewrite Dev A or Dev B's core implementation.

If you discover bugs in their modules, reproduce and document them, identify the responsible owner and report the issue.

Do not silently fix developer-owned code.

## 6. Documentation continuity is mandatory

After every meaningful milestone, update:

`docs/VALIDATOR_HANDOFF.md`

and:

`docs/VALIDATION_LOG.md`

Record:

- Completed work.
- Exact commands executed.
- Actual test results.
- Files modified.
- Current commit and branch.
- Remaining tasks.
- Known failures.
- Exact next action.

If context or usage is running low, update the handoff before doing anything else.

The repository must remain usable as the persistent source of truth across Claude and Codex sessions.

## 7. Working style

Do not flood me with explanations or raw terminal output.

Work autonomously, but explain important changes in simple language.

For each milestone, tell me:

- What you checked.
- What you found.
- What you changed.
- Which tests passed or failed.
- What remains.

Never claim a test passed unless you actually executed it.

Do not modify frozen experiment configurations or seeds to produce more favourable results.

Do not commit or push without permission.

## 8. FIRST RESPONSE

Start by reading the handoff documentation and inspecting Git state.

Then give me a concise report:

1. What Opus completed.
2. What Opus left incomplete.
3. Whether the JSON integration fix is actually working.
4. Whether there are uncommitted changes that must be preserved.
5. The exact next task you intend to perform.

After that, continue working. Do not stop at providing a report.

Your objective is to seamlessly continue Claude Opus's work and leave SAMG independently validated, with a functional dashboard and complete documentation.
