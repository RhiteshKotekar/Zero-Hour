# SAMG: How the Security and Learning Layer Solves the Problem

This document explains the part of SAMG that is built so far: how agents are identified, how their reports are checked, and how the learner is protected from false reports. It covers what problem each part solves and how each part works.

---

## Part 1: The problem and how we solve it

### The problem

SAMG simulates a team of autonomous agents carrying out a mission. Before each mission, a learning system chooses how the team is organised:

| Topology | How the team is organised |
| --- | --- |
| Hierarchical | One coordinator; all communication goes through it. |
| Functional-cell | Sub-teams by capability, each with its own coordinator. |
| Distributed | Agents that depend on each other talk directly. |

No single structure is best for every mission. So the system **learns** from past missions which structure works best for which kind of mission.

To learn, it needs to know how each mission went, and **the agents report that themselves**. That raises the core question:

> **What happens if an agent lies?**

Making agents sign their reports cryptographically is the obvious defence, and it is not enough. A digital signature proves **who** sent a report. It says nothing about whether the report is **true**. A compromised agent still holds its real key, so it can sign a false report that passes every signature check.

If the learner trusts signed reports, an attacker can feed it false successes, for example "the distributed topology scored 0.98". The learner then shifts toward whatever structure the attacker wants. This is **learning poisoning**, and the signature check never notices it.

### Our solution in one sentence

> **Treat every agent report as an untrusted claim, check it against independent evidence, and let the learner update only from outcomes the system has verified itself.**

The component that does this is the **Assurance Control Plane (ACP)**. It sits between the agents and the learner:

```text
        Agents (may lie)                Independent witness
   sign claims about their tasks     signs what actually happened
                │                               │
                └───────────────┬───────────────┘
                                ▼
            ┌─────────────────────────────────────────┐
            │       ASSURANCE CONTROL PLANE (ACP)       │
            │  ① Authentic?  Correct, registered key    │
            │  ② Fresh?      Not replayed, current epoch │
            │  ③ Allowed?    Own task, legal transition │
            │  ④ True?       Matches witness evidence   │
            │  ⑤ Admit?      Reward recomputed by ACP   │
            └─────────────────────────────────────────┘
                                │
                     only ADMITTED episodes
                                ▼
            ┌─────────────────────────────────────────┐
            │  LEARNING GATE (inside the learner too)   │
            └─────────────────────────────────────────┘
                                ▼
                    LinUCB topology learner
```

Three design rules make this work:

1. **A signature proves authorship, not truth.** Passing the signature check only means "this agent really said this". The ACP still has to decide whether the claim is true.
2. **The reward is never taken from a claim.** The ACP recalculates the mission reward from witness-verified outcomes. An agent's claimed number has no effect on the protected learner.
3. **Defence in depth.** The learner checks eligibility itself, and the database enforces "learn from each mission at most once", so a mistake in the wiring code cannot open a hole.

### How we prove it

The project compares two learners that start from **identical** state and receive the **same** stream of missions and attacks:

| | Protected learner | Vulnerable learner (`VulnerableLinUCB`) |
| --- | --- | --- |
| Learns from | ACP-admitted episodes only | Any correctly signed claim |
| Reward used | Recomputed by the ACP from evidence | The agent's own claimed reward |
| Signed false report | Blocked; state unchanged | Accepted; state shifts toward the attacker's choice |

A test in the repository already shows this at unit level. The same poisoned event is given to both learners. The vulnerable learner's internal matrices change. The protected learner refuses the event, and its matrices stay **byte-for-byte identical** to where they started.

### What is built so far

| Component | Problem it solves | Status |
| --- | --- | --- |
| Shared data contracts | Every module agrees on exactly what a report, decision, episode and learning event look like | ✅ Done |
| Canonical encoding | Signer and verifier always hash the exact same bytes | ✅ Done |
| Identities and signatures | Proves who sent each report; detects forgery and tampering | ✅ Done |
| Freshness and replay protection | Stops old valid reports being resent | ✅ Done |
| Task state machine | Stops agents claiming things they have no authority to claim | ✅ Done |
| Learners (LinUCB, UCB1, baselines, vulnerable) | Picks the topology; supplies the comparisons for the experiments | ✅ Done |
| Learning gate | Guarantees only verified outcomes reach the learner | ✅ Done |
| Append-only audit database | Keeps every attempt, including blocked attacks, and lets nobody rewrite history | ✅ Done |
| Contract fixtures | Gives every team member the same honest, false and replayed test cases | ✅ Done |
| Witness service, corroboration, episode admission (steps ④–⑤) | Checks whether claims are **true** | ⏳ Next (Phase 2) |
| Mission, topology graph, allocation, simulator, reward | Generates what actually happened (Dev A) | ⏳ Not started |
| End-to-end CLI, experiments, dashboard | Runs and shows the full demonstration | ⏳ After the above |

80 automated tests pass. Two more tests wait for Dev A's mission model.

---

## Part 2: How each part works

### 2.1 Shared data contracts
**File:** `src/samg/domain/events.py`, `src/samg/domain/enums.py`

**What it is.** These are the typed "forms" passed between modules, written as Pydantic models. Any malformed form is rejected the moment it is created.

| Model | Meaning |
| --- | --- |
| `AgentEvent` | A signed **claim** by an agent, such as "I started T2", "I completed T2" or "the reward was 0.98". Untrusted. |
| `WitnessEvent` | A signed **observation** by the independent witness, such as "T2 went from EXECUTING to FAILED at 2000 ms". |
| `EventDecision` | The ACP's verdict on one event, with machine-readable reason codes. |
| `EpisodeRecord` | The ACP's verdict on a whole mission: `ADMITTED`, `PROVISIONAL` or `REJECTED`. |
| `LearningEvent` | The only thing a learner is allowed to see. |

**Why it matters for the solution.** The trust rules are built into the models themselves:
- An `EpisodeRecord` may carry a reward **only if** it is `ADMITTED`.
- A `LearningEvent` records where its reward came from: `ACP_RECOMPUTED` or `AGENT_CLAIM`. A protected learner accepts only `ACP_RECOMPUTED`.
- An event decision that rejects something must say why, with a reason code.

So the rules hold even if some other code path makes a mistake: an invalid combination can't be created at all.

### 2.2 Canonical encoding: deciding exactly what gets signed
**File:** `src/samg/domain/canonical.py`

**The problem.** A signature is computed over **bytes**, not over meaning. Take these two JSON texts:

```text
{"task":"T2","agent":"A1"}
{"agent":"A1","task":"T2"}
```

They mean the same thing but are different bytes, so a signature over one fails on the other. Time zones (`05:30+05:30` and `00:00Z` are the same instant) and float rounding cause the same problem. Without one fixed byte format, honest reports would randomly fail verification.

**How it works.** `canonical_bytes()` is the **only** function that turns data into bytes for signing or hashing:

| Rule | Example |
| --- | --- |
| Keys sorted, no spaces | `{"agent":"A1","task":"T2"}` |
| Times converted to UTC with microseconds | `2026-01-01T00:00:02.600000+00:00` |
| Times without a time zone rejected | Ambiguous, so not allowed |
| Floats rounded to 9 decimals; NaN and infinity rejected | `0.1 + 0.2` becomes `0.3` |
| Enums written as plain text | `"DISTRIBUTED"` |

Every event has `signed_payload_bytes()`, which encodes every field except the signature itself.

**Safety detail.** The signed bytes include a `kind` field, `AGENT_EVENT` or `WITNESS_EVENT`. An agent's signed claim therefore can never be passed off as a witness observation.

**How we keep it stable.** A **golden test** stores the exact bytes and signature of one sample report. If anyone changes the format, even by accident, that test fails immediately. This matters because two developers are writing code that must agree byte for byte.

### 2.3 Identity: who is allowed to speak
**File:** `src/samg/assurance/identity.py`

**What it is.** Every participant, including each agent and the witness, has:
- an **Ed25519 key pair**, the same modern signature algorithm used by SSH and Signal;
- a **role**: `AGENT`, `COORDINATOR` or `WITNESS`;
- a **key ID**, for example `A1#a69eb99b0d04`: the agent name plus a short fingerprint of its public key.

**How keys are made.** Keys are derived from the scenario seed:

```text
private key seed = SHA-256("samg-ed25519-v1|<scenario seed>|<agent id>")
```

- The same scenario seed always gives the same keys, so every experiment can be replayed exactly.
- Adding a new agent never changes the other agents' keys.

**Where keys live.**

| Store | Contains | Persisted? |
| --- | --- | --- |
| `KeyRing` | Private keys (used only by simulated signers) | **Never.** It lives only in memory and even its printout hides the keys. |
| `IdentityRegistry` | Public keys, roles, active flag | Yes. This is what the ACP uses to verify. |

A test checks that no database column and no identity record contains private key material.

### 2.4 Signatures and verification: proving who said it
**File:** `src/samg/assurance/signatures.py`

**Signing:**

```text
bytes     = event.signed_payload_bytes()
signature = Ed25519_sign(private_key, bytes)        # 64 bytes
event.signature = URL-safe base64(signature)
```

**Verification** runs these checks in order and stops at the first failure:

| # | Check | If it fails | What attack it stops |
| --- | --- | --- | --- |
| 1 | Signature present and correctly encoded | `MALFORMED` | Garbage input |
| 2 | `key_id` is registered | `UNKNOWN_KEY` | An outsider inventing an identity |
| 3 | The key belongs to the agent named in the report | `KEY_AGENT_MISMATCH` | Agent A0 signing a report "from A1" |
| 4 | That identity is still active | `INACTIVE_IDENTITY` | A revoked agent |
| 5 | Ed25519 signature is valid for these exact bytes | `BAD_SIGNATURE` | Any change after signing, even one character |

**What passing means, and what it doesn't.** Passing means "this registered agent really signed exactly this report". It does **not** mean the report is true. That is why verification is only the first step of the ACP.

### 2.5 Freshness and replay protection: is this report new?
**File:** `src/samg/assurance/freshness.py`

**The attack.** An attacker records a genuine, correctly signed report, such as "T2 completed successfully", and resends it later or in another mission. The signature is still perfectly valid.

**How we stop it.** Each report carries:
- the **mission ID** and **epoch**, a version number for the current mission run;
- a **sequence number**, counting each signer's messages.

| Check | Result |
| --- | --- |
| Report belongs to an unknown mission | `REJECTED: WRONG_MISSION` |
| Report is from an old epoch | `STALE: OBSOLETE_EPOCH` |
| Same event ID seen before | `DUPLICATE: DUPLICATE_EVENT_ID` |
| Same `(mission, epoch, signer, sequence)` seen before | `DUPLICATE: DUPLICATE_SEQUENCE` |
| Timestamp too far in the future (more than 5 s) | `REJECTED: CLOCK_SKEW` |
| Timestamp too old (more than 300 s) | `STALE: EVENT_TOO_OLD` |

Epoch and sequence are the main defence. The timestamp is a secondary sanity check, because the simulation runs on simulated time.

**Two important details.**
- **It survives a restart.** The database has a UNIQUE rule on `(mission, epoch, signer, sequence)`. Even after a crash, a replayed report is still caught. A test closes the database, reopens it and replays the report.
- **Forgeries can't burn sequence numbers.** A sequence number is recorded as "used" only after the signature is verified. Otherwise an attacker could send forged reports using an honest agent's next numbers and block its real reports.

### 2.6 Task state machine: is this claim even allowed?
**File:** `src/samg/assurance/state_machine.py`

Each task moves through fixed states:

```text
OPEN → ASSIGNED → EXECUTING → REPORTED_COMPLETE → VERIFIED_COMPLETE
                     │                │
                     └──── FAILED ◄───┘           (plus BLOCKED)
```

| Rule | Why |
| --- | --- |
| Agents can only move a task to `EXECUTING` or `REPORTED_COMPLETE` | An agent can **claim** completion but never **certify** it |
| Only the witness can set `VERIFIED_COMPLETE` or `FAILED` | Truth comes from an independent source |
| No jump from `ASSIGNED` straight to `VERIFIED_COMPLETE` | A task must actually run first |
| Agents may only report on tasks assigned to them | One agent can't make claims about another's work |
| `VERIFIED_COMPLETE` and `FAILED` are final | Outcomes can't be rewritten afterwards |

The **task ledger** keeps the official state of each task, built **only from witness observations**. Agent claims are checked against this ledger, and never change it.

A property-based test (Hypothesis) generates hundreds of random sequences of moves and checks that none of them can break these rules.

### 2.7 Witness evidence and corroboration: is the claim true? *(Phase 2, next)*

This is the step that catches the signed liar. Here is the scenario from our shared test fixture `04_false_signed_claim.json`:

| Source | Says |
| --- | --- |
| Agent A1 (correctly signed, fresh, authorised) | "I completed T2", then "the reward was 0.98" |
| Witness (its own separate key) | "T2: EXECUTING → **FAILED** at 2000 ms" |

Every check so far passes for A1's claim: it is authentic, fresh and allowed. Only the comparison with the witness exposes the lie, so the claim becomes **`DISPUTED`** and is quarantined.

The planned rules:
- A claim the witness confirms is `CORROBORATED`.
- A claim the witness contradicts is `DISPUTED`.
- A claim with no witness evidence is `PROVISIONAL`. It is not believed, but not called a lie either.

Then the whole mission episode is judged:
- **`ADMITTED`** only if the witness covers every reward-critical task. The ACP **recomputes the reward** from those verified outcomes. In the example above, the learner learns that T2 failed, which is the truth, and not the claimed 0.98.
- **`PROVISIONAL` or `REJECTED`** otherwise, and the learner learns nothing.

### 2.8 The learners: choosing the team structure
**Folder:** `src/samg/learning/`

| Name | What it does | Role in the experiments |
| --- | --- | --- |
| P0-H / P0-F / P0-D | Always uses one fixed topology | Simple baselines |
| P1 | Uses whichever fixed topology was best in training | Strong baseline that doesn't adapt |
| P2: UCB1 | Learns which topology is best on average and ignores mission details | Shows whether mission context matters |
| **P3: LinUCB** | Learns which topology is best **for this kind of mission** | **Our adaptive method** |
| S1: `VulnerableLinUCB` | LinUCB that trusts any signed claim | The deliberately unsafe comparison; only built on request, never the default |

**How LinUCB works.** Each mission is described by a short feature vector, for example how dependent the tasks are, how varied the agents' skills are, and how scarce resources are. For each topology, LinUCB keeps a running estimate of "expected reward given these features". Before a mission it scores each eligible topology:

```text
score = expected reward  +  exploration bonus
```

- The **expected reward** is learned from past verified missions.
- The **exploration bonus** is large when that topology hasn't been tried much for missions like this one. This makes the system try under-explored options instead of locking in early.

It picks the highest score. After the mission, **if the ACP admitted the episode**, it updates that topology's estimate with the ACP's recomputed reward.

**Engineering details that make results trustworthy:**
- **Deterministic:** a seeded warm-up tries each topology once, and ties are broken by a fixed order. The same inputs always give the same decisions.
- **Numerically safe:** it solves linear systems instead of inverting matrices.
- **Auditable:** every decision records each topology's score, expected reward and exploration bonus.
- **Cloneable:** its state can be saved and restored exactly. That is how the protected and vulnerable learners start from identical state for a fair attack comparison.
- **Hand-checkable:** a test matches one update against the textbook formula, which our validator can recompute independently.

### 2.9 The learning gate: the final guarantee
**Files:** `src/samg/learning/base.py`, `src/samg/domain/events.py`

Every protected learner, whether LinUCB, UCB1 or a fixed baseline, passes each `LearningEvent` through the gate before touching its state:

| Check | Refusal reason |
| --- | --- |
| Episode status is `ADMITTED` | `INELIGIBLE_STATUS` |
| Reward source is `ACP_RECOMPUTED`, not an agent's claim | `UNTRUSTED_REWARD_SOURCE` |
| This episode hasn't been learned from already | `DUPLICATE_EPISODE` |

On refusal, the learner raises an error, logs the attempt, and its state stays **exactly unchanged**. The tests confirm this byte for byte.

The same rule is enforced in three independent places:
1. by orchestration, before it calls the learner;
2. by the learner itself, through the gate;
3. by the database, which allows at most one applied update per learner per episode.

### 2.10 Audit database: nothing can be hidden or rewritten
**Files:** `src/samg/persistence/db.py`, `src/samg/persistence/repositories.py`

A local SQLite database records the full chain for every mission: configuration, mission, topology decision, allocation, outcome, every received report, every ACP verdict, every episode, every learning attempt, and learner snapshots.

| Property | How |
| --- | --- |
| **Append-only** | Database triggers block every UPDATE and DELETE. History can't be edited, even by our own code. |
| **Blocked attacks are visible** | Rejected and replayed reports are still stored, with their reason codes. The dashboard can show "40 attacks attempted, 0 learned from". |
| **Trusted and quarantined data kept apart** | Admitted episodes go in `episodes_trusted`; provisional and rejected ones go in `episodes_quarantined`. |
| **Durable replay barrier** | UNIQUE rule on `(mission, epoch, signer, sequence)` |
| **Durable once-only learning** | UNIQUE rule on (learner, episode) for applied updates |
| **No secrets** | No private key is ever stored |

### 2.11 Shared test fixtures
**Folder:** `tests/contract/fixtures/`

Five fixed scenarios that every team member's code is tested against:

| Fixture | Scenario | Expected result |
| --- | --- | --- |
| `01_reachable_mission` | 2 agents, task T1 → T2, handoff possible | Feasible under every topology |
| `02_unreachable_mission` | Same, but no communication path | Infeasible; reported, not hidden |
| `03_honest_claim` | A1 honestly claims T2 done; witness confirms | Authenticated, then corroborated |
| `04_false_signed_claim` | A1 signs a false completion and a 0.98 reward; witness saw FAILED | Authenticated, then **disputed** |
| `05_replayed_event` | Resent report, reused sequence number, old epoch | Duplicate, duplicate, stale |

The fixtures are generated by a script and signed with real keys. A test fails if they ever drift from what the code would produce.

---

## Part 3: Scope and honest limits

The ACP protects against unknown identities, forged or tampered reports, impersonation, replays, unauthorised claims, and **correctly signed but false claims** (with the witness, Phase 2).

It does **not** protect against:
- a compromised witness, or a majority of colluding evidence sources;
- stolen keys used outside the simulation;
- network confidentiality or denial of service;
- physical-world sensor integrity.

SAMG is a controlled, seed-reproducible simulation, not a live robotics system. Stating these limits up front is part of the design, so results are never overclaimed.
