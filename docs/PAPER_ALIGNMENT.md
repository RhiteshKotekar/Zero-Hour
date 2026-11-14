# Paper Alignment — Neural Combinatorial Optimization on Heterogeneous Graphs

This document maps SAMG onto the approach and constraints of the paper below. It records the design for a **deferred, optional, local-only neural allocator baseline** that follows the paper:

> Laurin Luttmann and Lin Xie. **"Neural Combinatorial Optimization on Heterogeneous Graphs: An Application to the Picker Routing Problem in Mixed-Shelves Warehouses."** *Proceedings of the 34th International Conference on Automated Planning and Scheduling (ICAPS 2024)*, pp. 351–359. DOI [10.1609/icaps.v34i1.31494](https://doi.org/10.1609/icaps.v34i1.31494). Code (MIT): [github.com/LTluttmann/rl4msprp](https://github.com/LTluttmann/rl4msprp).

The paper is referred to as **[P]**. It has no numbered sections, so references use its section titles (e.g. [P: MDP › Action]), equation numbers (Eq. 1–19) and table numbers. The hackathon brief is referred to by `§`. Decisions are recorded as D022–D029 in [DECISIONS.md](DECISIONS.md).

**Status (team decision, 2026-11-14):**

- The neural allocator is **not part of the hackathon MVP**. It is a comparison baseline for later work and runs only on one developer's laptop, which has an Intel Arc XPU.
- The hackathon deliverable stays inside brief §2.2.
- Experiments A–C use **CP-SAT** with the greedy fallback.
- The neural baseline appears only in an optional, later **Experiment E**, run locally.

**No arXiv version of this paper exists.** The arXiv API lists no entry, and Semantic Scholar records only DBLP and DOI identifiers. The arXiv paper by the same authors, [arXiv:2502.10233](https://arxiv.org/abs/2502.10233) ("Learning to Solve the Min-Max Mixed-Shelves Picker-Routing Problem via Hierarchical and Parallel Decoding", 2025), is a multi-agent follow-up (MAHAM). It is mentioned here only for context. SAMG does not adopt it, because it is multi-agent RL, which stays out of scope (D022).

## 1. Paper summary

### 1.1 Problem and constraints

The Mixed-Shelves Picker Routing Problem (MSPRP) is about storage. Units of one SKU are spread over several shelves, so a picker must choose **which shelf to take each SKU from** as well as **the route**. Selection and routing are decided together [P: Introduction]. The paper's MIP (Eq. 1–11) minimises the total distance `Σ D_ij x_ijb` over tours `b ∈ B`, subject to:

| Constraint | [P] equation | Meaning |
| --- | --- | --- |
| Flow conservation | (2) | A visited location is also left. |
| Visit once per tour | (3) | At most one visit to a storage location per tour. |
| Pick only where visited | (4), `M = κ` | Units are taken only from locations on the tour. |
| Depot start/end | (5) | Each tour leaves the packing station exactly once (and returns via (2)). |
| Subtour elimination | (6) | No disconnected cycles. |
| Capacity | (7) | At most `κ` units per tour. |
| Demand satisfaction | (8) | Every SKU's demand `d_p` is met exactly. |
| Supply limit | (9) | No more than `n_i` units are taken from a location. |
| Domains | (10–11) | `x` binary, `y ≥ 0`. |

Simplifying assumptions [P: Formal Definition]: a single depot, split orders and split deliveries (one SKU's demand may be split across tours and shelves), and single-SKU orders. `|B| = ⌈Σ d_p / κ⌉`. Instances place shelves uniformly at random in the unit square with Euclidean distances. The authors choose this over a realistic rectangular layout [P: Dataset].

### 1.2 MDP and heterogeneous graph state

[P: MDP for the Heterogeneous Graph MSPRP]:

- **State** `s_t = G = (V, P, E_t, c_t)`. The graph has **two node types**. *Locations* `V` (the depot `h` plus the shelves) carry 2-D coordinates. *SKUs* `P` carry the remaining demand `d_{p,t}`. **Weighted shelf–SKU edges** carry the current supply `e_{ip,t}`. A **context node** `c_t` holds the picker's current location and remaining capacity `κ_t`. The paper rejects a homogeneous one-hot storage-location encoding because it is not **instance-size agnostic**.
- **Action** `a_t = (i, p)`, a composite shelf–SKU pair. Feasibility is enforced by masking:
  - a shelf is feasible only if it can satisfy demand for at least one SKU still in demand;
  - an SKU is feasible only if it is available at the chosen shelf;
  - the depot is always allowed except for two depot visits in a row;
  - when capacity is exhausted, the depot is the only allowed action;
  - a dummy SKU `|P|+1` pairs with the depot;
  - tours start and end at the depot.
- **Transition** is deterministic. The picker always takes the maximum feasible quantity, `min(supply, demand, remaining capacity)`, and supply, demand and capacity are updated. A depot visit resets the capacity.
- **Reward** `R(τ)` = −(total distance), i.e. the negative of Eq. 1. It is given once, for the complete solution `τ`.

### 1.3 Model

- **Encoder: Heterogeneous Attention Model (HAM)** [P: Encoder, Fig. 1].
  1. Type-specific linear projections map each node type into a shared space of size `d_h`.
  2. Per-type **multi-head self-attention** (MHSA) with skip connection and LayerNorm learns intra-type relations, such as which shelves can substitute for each other.
  3. MatNet-style **cross-attention** between types (Eq. 13–17) learns inter-type relations. HAM changes MatNet in one place: it replaces MatNet's feed-forward mixing of score and edge weight with a plain product `α'_ij · e_ij`, which the authors report is better and faster.
  4. The configuration is `L = 4` layers, `d_h = 256` and 8 heads.
- **Decoder: hierarchical** [P: Decoder, Eq. 18, Fig. 2]. The composite action space `A = A_V × A_P` is factorised as `π(a_t|s_t) = π_V(i_t|s_t) · π_P(p_t|s'_t)`. Here `s'_t` is an intermediate state after a partial transition that updates only the location. The two sub-policies share the encoder but have separate attention decoders in the style of the Attention Model (AM). Each decoder builds its query from the context (current-location embedding ⊕ remaining capacity), computes a glimpse, and produces logits that are masked and softmax-normalised. The point of the factorisation is that the action space grows linearly with instance size instead of combinatorially.
- **Training: Policy-aware POMO (Pa-POMO)** [P: Training, Alg. 1, Eq. 19].
  - The gradient estimator is REINFORCE with a shared per-instance baseline: the mean reward of `W` rollouts.
  - Unlike POMO, the `W` starting actions are **sampled from the policy without replacement**, because a random first shelf can be very poor.
  - One warm-up epoch uses an exponential-moving-average baseline.
  - Optimiser and scale: Adam at lr 2e-4, `W = 10`, batch 512 (256 for PRP100), 50 epochs × 350,000 instances generated on the fly.
- **Inference**: beam search with width 100 at test time [P: Model Configuration].

### 1.4 Evaluation protocol and results

- **Instance types**: PRP20/50/100 (20/50/100 storage locations; 10/25/40 shelves), with `|P|`, mean supply `n̄_i` and `κ` varied as in Table 2. Demand is clipped to total supply so every instance is feasible.
- **Encoder ablation** (Table 3): HAM beats MatNet, HGCN, AM (homogeneous graph) and HAN on all six PRP20/50 settings, using 30,000 test instances each.
- **Decoder ablation** (Table 4): the hierarchical decoder beats a flat combinatorial decoder and a hybrid decoder (neural shelf choice plus greedy SKU choice). The flat decoder degrades as size grows.
- **Comparison with solvers** (Table 5), on 20 test instances per type:
  - **Gurobi** with 1/3/5 h time limits solves all PRP20 instances to optimality, and **HAM + beam search matches it (0.0 % gap)**.
  - On PRP50/100, Gurobi does not reach optimality (gaps up to 20.8 %), and HAM is best everywhere.
  - HAM also beats the VNS heuristic of Xie, Li and Luttmann (2023), with 1.1–2.8 % gaps on the larger instances.
  - HAM inference takes 0.14–0.60 s, but **training took 4–27 h on an NVIDIA A100-80GB**.
- **Stated limitations** [P: Conclusion]:
  - attention is quadratic in instance size, which hinders real-world instances;
  - training times are already very long;
  - the hybrid approach is limited to local, greedy information.

  Future work: multiple GPUs, more efficient attention, training small and generalising large (light encoder / heavy decoder). Further limitations that follow from the paper's design: a single picker and single depot, unit-square Euclidean layouts, and split deliveries.

### 1.5 Implementation facts that matter here

The official repository was checked: its README, `setup.py` and the encoder sources. It depends on `torch>=1.13`, `hydra-core`, `neptune` and `gurobipy==10.0.0`. **It does not use PyTorch Geometric.** The HAM, HAN and HGCN encoders (`comb_encoder.py`, `han_encoder.py`, `het_gcn.py`) are plain `torch.nn` code, so the model family can be benchmarked on Intel XPU (see §6).

## 2. Mapping SAMG → paper

| SAMG concept | Paper concept | Fit |
| --- | --- | --- |
| Mission graph (NetworkX `MultiDiGraph`, node kinds mission/task/agent/capability/role, §5.1) | Heterogeneous state graph `G = (V, P, E_t, c_t)` | Partial. The paper's graph is an **encoder input view**, not the system's source of truth. SAMG derives a two-type view (agents, tasks) plus a context node from the typed graph (D023). |
| Agent (capabilities, capacity, budget, availability) | Shelf/location node (supplies SKUs) | An agent "supplies" capability-hours, as a shelf supplies SKU units. |
| Task (required capabilities, duration, demand, priority) | SKU node (demand `d_p`) | A task is the demand to cover. SAMG requires **exactly one** assignee per task, so split deliveries are **not** adopted. |
| `CAN_PERFORM` / capability match (agent → capability ← task) | Weighted shelf–SKU edge `e_ip` (supply) | Capabilities are folded into a weighted task–agent eligibility edge. This is the "mixed shelves" property: the same capability is available from several agents (substitutability). |
| `COORDINATES_WITH` paths and hop distances (topology-dependent) | No counterpart. Intra-type relations are *learned* by MHSA | **Extension required.** Agent–agent hop distances and task–task `DEPENDS_ON` edges enter as intra-type attention biases. Without this, the topology would not reach the encoder (D024). |
| Agent capacity / resource budget | Picker capacity `κ` (Eq. 7) and supply `n_i` (Eq. 9) | Direct. Both are enforced by masking. |
| Precedence `DEPENDS_ON`, start times, handoff delay | No counterpart (routing order only) | **Extension.** A task is selectable only when all its predecessors have been assigned. The schedule is computed in the transition. |
| Unreachable handoff = infeasible (§5.4) | No counterpart | **Extension.** An agent is masked if any assigned predecessor's agent has no permitted path to it. |
| Graph-derived handoff cost `H(A,G_O)`, allocator objective `λ_T C_max + λ_R R + λ_H H` (§7.1) | Objective Eq. 1, reward = −distance | Direct analogue: reward = −(the same weighted allocation objective CP-SAT minimises). |
| CP-SAT allocator (§7.1) | Gurobi MIP baseline (Table 5) | **The MVP allocator** and, for the later baseline, the **exact reference**, as the paper keeps Gurobi as the exact comparator. |
| Deterministic greedy fallback (§7.1) | VNS heuristic / greedy nearest-neighbour start | Kept as the **heuristic baseline** and the hard fallback. |
| *(later, optional)* Neural allocator baseline | HAM encoder + hierarchical decoder, Pa-POMO, beam search | **Deferred.** It would sit behind the same `allocate()` interface as a comparison baseline, run locally only (D022). |
| LinUCB topology selector (§6) | None | Unchanged. The paper does not address meta-level structure selection. |
| ACP evidence gate (§8) | None (training reward comes from the deterministic environment) | Unchanged. If the baseline is enabled, the gate is extended to cover its training data and model artefacts (D026). |
| Simulator (§10) | Deterministic transition function `Γ•` | Separate concerns. `Γ•` is a *planning-time* MDP inside the allocator; the simulator still executes the resulting plan with seeded noise. |
| Experiments A–D (§12) | Encoder/decoder ablations, solver comparison | A–C use CP-SAT. An optional, later **Experiment E** compares allocators locally, with an optional size sweep and an optional allocator-sensitivity rerun of Experiment A (D029). |

## 3. Verdict per SAMG component

| Component | Verdict | Reason |
| --- | --- | --- |
| Typed mission graph (`domain/graph.py`, `topology/builder.py`) | **Keep**; a derived view is added only with the baseline | §5.1 makes it the single source of truth. The paper's state graph becomes a deterministic tensorisation (`nco/features.py`), ordered by ID, regenerated from the typed graph at every step [P: MDP › State]. |
| Topology templates and `handoff_cost` (§5.3–5.4) | **Keep** | They feed three places: the reward, the masks and the encoder's agent–agent bias. If the baseline is built, the "graph is executable" invariant must hold for it as well. |
| Context features `ctx-v1` and LinUCB / UCB1 (§6) | **Keep** | Three arms and a 5-D context. The paper offers nothing for this, and a contextual bandit is still the right tool. The neural allocator is not a topology selector. |
| CP-SAT allocator | **Keep** | It is the MVP allocator for every experiment. Later, it is also the exact reference for Experiment E gap computation [P: Table 5] and the oracle for the baseline's mask tests. |
| Greedy fallback | **Keep** | Heuristic baseline and last-resort fallback, unchanged. Later, it is also used when a neural plan fails validation. |
| Allocation constraint checker | **Add later**, with the baseline (`allocation.validate_plan`) | A plan from any solver, neural included, is re-checked before simulation. Masks are a construction aid, not a proof (INV-12). |
| Neural constructive allocator | **Add later**: deferred, optional, local-only comparison baseline (`nco/`) | It follows [P] closely: heterogeneous graph state, HAM encoder, hierarchical decoder with feasibility masks, Pa-POMO training, greedy and beam decoding. It is extended for precedence, path reachability and intra-type edges, and simplified because SAMG has no depot or tours and does not split tasks. |
| Simulator, witness, reward (§7.2) | **Keep** | The paper's reward is a planning objective, not the mission reward. The mission reward `0.65C + …` stays the bandit's signal. |
| ACP, admission and guarded update (§8) | **Keep**; extend only with the baseline | In the MVP INV-05 applies exactly as written. If the baseline is enabled, INV-05 is restated for online state, and INV-10 to INV-13 are added for training provenance, checkpoint integrity, post-decode validation and split disjointness (D026). |
| Persistence | **Extend later** | Append-only `model_checkpoints`, `nco_training_runs` and `allocator_evaluations` tables, added only with the baseline. |
| Experiments A–D | **Keep**; optional later E | Experiments A–C use **CP-SAT** for every policy (§7.1, D029). The baseline gets only its own optional Experiment E, following the paper's protocol. |
| Dashboard | **No MVP change** | Later, optionally: show the solver used, checkpoint hash and fallback flag for Experiment E runs. |

### 3.1 Concrete SAMG allocation MDP (adapted from [P]; deferred baseline)

| Element | SAMG definition |
| --- | --- |
| Node type *task* | Duration, resource demand, priority weight, `mandatory`, `reward_critical`, in-degree and out-degree, critical-path depth, assigned flag, earliest start. All values are normalised; no one-hot IDs, so the encoding stays size-agnostic. |
| Node type *agent* | Capacity remaining, resource budget remaining, `available`, `can_coordinate`, the time it next becomes free, load so far. |
| Task–agent edge | Capability-fit weight (1 if the agent holds every required capability, 0 otherwise). It multiplies the cross-attention scores, `α'_ij · e_ij`, as in [P] Eq. 15 modified. |
| Agent–agent intra edge | `−β · hops` in the selected topology, or `−∞` if there is no path. Added as a bias to agent MHSA. This deviates from [P] and is required so that the encoder sees the topology. |
| Task–task intra edge | Additive bias for `DEPENDS_ON` in both directions. This also deviates from [P]. |
| Context node | Last assigned (task, agent) embedding, makespan so far, fraction of tasks assigned. The query is built from it [P: Decoder]. |
| Action | Composite `(task, agent)`, decoded hierarchically: `π(t, a | s) = π_T(t | s) · π_A(a | s', t)`. |
| Task mask | Unassigned, and every predecessor already assigned. |
| Agent mask | Available; holds the required capabilities; capacity and budget not exceeded; and a permitted path exists from each predecessor's agent (§5.4 "infeasible"). |
| Dead end | No task can be selected but tasks remain unassigned. The result is a structured infeasible result, never a silent partial plan. |
| Transition `Γ•` | Assign the task. Set its start to the latest of its predecessors' ends plus handoff delay, and the agent's free time. Then update the agent's free time, capacity and budget. Fully deterministic, as in [P]. |
| Reward | `R(τ) = −(λ_T C_max + λ_R R(A) + λ_H H(A, G_O) + λ_L load + λ_U unserved)`, using `config/allocation.yaml` weights, computed by `allocation.common.evaluate`. It is the same function CP-SAT minimises, so gaps are comparable. |

## 4. Conflicts with the brief and their resolution

The team decided on 2026-11-14 to keep the neural allocator out of the hackathon MVP and to use CP-SAT for Experiments A–C. That decision removes every conflict for the hackathon deliverable. The rows below record how each conflict is resolved, and the constraints that apply if the baseline is built later.

| # | Conflict | Brief | Resolution (decision) |
| --- | --- | --- | --- |
| C1 | Neural / GNN components are banned | §2.2 "Do not add HMMs, GNNs, multi-agent reinforcement learning …"; §14.1 rule 9 "Do not add neural … or additional learning components" | **Resolved: no exception needed.** The hackathon deliverable contains no neural component, so §2.2 and §14.1 rule 9 are respected (D022). The HAM-style allocator is post-MVP, optional, local-only comparison work. MARL (including the MAHAM follow-up), HMMs, LLMs, neural memory, federated learning and blockchain stay out of scope for later work too. |
| C2 | Second learning method | §6.5 "do not introduce a second complex learning algorithm" | **Not applicable to the MVP.** Later, the baseline is trained **offline**, then **frozen** and hash-pinned, and acts as a fixed function in Experiment E. LinUCB (with UCB1 as its baseline) stays the only *online* learner (D025). |
| C3 | Allocator must be held constant | §7.1 "The allocator is held constant across all experimental configurations" | **Resolved:** Experiments A–C use CP-SAT for every policy (D029). Neural results appear only in the optional Experiment E, and in an optional local allocator-sensitivity rerun of Experiment A that is reported separately. |
| C4 | 24-hour window versus 4–27 h of A100 training | §14 hour plan; H14 vertical slice | **Resolved:** no neural work happens in the 24-hour window (D028). Later, SAMG instances are tiny (judge mission 8 tasks and 6 agents; generator missions about 16 tasks at most), so the model is scaled down (§6) and training is capped at about 3 h on the laptop XPU. |
| C5 | Determinism | §5.3, §12.7, repo rule "every RNG takes an explicit seed" | MVP is unaffected. For the baseline: bitwise training reproducibility on XPU is not promised. Reproducibility is defined at the **checkpoint**: SHA-256, config, seeds, torch version and device are recorded. Inference in recorded runs uses **CPU** with deterministic algorithms, greedy or beam decoding with a fixed tie-break, and a seeded `torch.Generator` for sampling. Same checkpoint + same inputs → same plan (D027). |
| C6 | "Only validated rewards may update the learner" (INV-05) | §4.4, §8.9 | **MVP: INV-05 unchanged.** For the baseline: **restated, not dropped** (D026). INV-05 governs the online topology learner. Training-time reward for the allocator is a *planning objective* computed by trusted code from generator instances; it never comes from agent reports, witness events or episodes. That requirement is now INV-10. Checkpoints are an integrity boundary (INV-11). INV-10 to INV-13 apply only while the baseline is enabled. Online fine-tuning of the allocator is not allowed. |
| C7 | "The graph must be executable" | §5.4, §12.10 | MVP: unchanged, enforced through CP-SAT's objective. If the baseline is built, the selected topology changes its masks (reachability), its encoder input (hop biases) and its objective. The §12.10 test "changing topology changes the objective or the assignment" and the `h0 = h1 = 0` ablation are repeated with the neural allocator (D024). |
| C8 | Judge Q&A "Why not deep RL?" | §16 | **The brief's answer stands for the hackathon.** If asked, mention the neural allocator baseline as planned post-hackathon comparison work, and claim no result. |
| C9 | Claims to avoid | §17.1 | Add: "neural allocator beats CP-SAT" unless Experiment E measures it. At SAMG's size, [P] itself only reports **parity** with an exact solver (PRP20, Table 5). Any advantage is expected only at larger instance sizes, through speed. |
| C10 | Compute | Brief assumes laptop CPU; [P] used an A100 | **The MVP needs no PyTorch, GPU or NPU.** The XPU is used only to train, and optionally benchmark, the deferred baseline. CPU is used for tiny models and recorded inference. **No PyTorch Geometric.** The NPU is optional and inference-only (D027). |

## 5. Restated invariants (apply only when the neural baseline is enabled)

In the MVP, INV-01 to INV-09 apply exactly as written in brief §8.9.

| ID | Invariant (restated or new) | Enforcement |
| --- | --- | --- |
| INV-05 (restated) | Only `ADMITTED` episodes can update **persistent online policy state** (LinUCB, UCB1). This covers any learner that changes during an experiment. | Guarded update API (unchanged) |
| INV-10 (new) | Allocator training instances come only from the seeded scenario generator, using the `nco-train` seed range. Training rewards come only from `allocation.common.evaluate` on those instances. No `AgentEvent`, `WitnessEvent`, `EpisodeRecord` or quarantined record (whether admitted or not) is ever a training input. | `nco/train.py` accepts only a generator handle and a seed range; a test asserts there is no persistence import in `nco/` |
| INV-11 (new) | A checkpoint is loaded only if its SHA-256 matches a `FROZEN` row in `model_checkpoints` and the run manifest. Loading uses `torch.load(..., weights_only=True)`. | `nco/checkpoint.py` |
| INV-12 (new) | Every neural plan passes `allocation.validate_plan` before simulation; CP-SAT and greedy plans may be checked too. A neural plan that fails is replaced by CP-SAT (or by greedy, if CP-SAT is unavailable), with `fallback_used = true` and a reason code. | `allocation.neural_adapter` |
| INV-13 (new) | The `nco-train`, `nco-dev` and `nco-test` instance seed ranges are pairwise disjoint, and also disjoint from the Experiment A dev/train/test seeds. | Validator script and manifest |

## 6. Compute plan (deferred baseline only)

**Nothing in the hackathon MVP needs PyTorch, the XPU or the NPU.** This plan covers only the later neural baseline, trained and evaluated on one developer's laptop. The XPU is used only to train, and optionally benchmark, that baseline. The laptop has an Intel Core Ultra 5 125H, Intel Arc iGPU, AI Boost NPU and 15.4 GB RAM, with **no NVIDIA GPU**.

| Item | Rule |
| --- | --- |
| Training device | Use Intel XPU (`device="xpu"`) for models of roughly ≥ 259k parameters, with **torch 2.15.0+xpu in a separate virtual environment**. The project `.venv` keeps CPU-only torch; do not replace it. Autoencoders of 259k–1M parameters trained 3.1–4.65× faster on XPU than on CPU on this laptop. |
| Tiny models | Use CPU. A ~7k-parameter model ran about 2× slower per epoch on XPU. The 7k–259k range is untested, so **time both devices** before choosing. |
| Encoder implementation | Plain PyTorch (`nn.MultiheadAttention` or hand-written scaled dot-product attention, `nn.LayerNorm`, `nn.Linear`), as in the official repository. **Do not use PyTorch Geometric.** `GCNConv` fails on XPU at every size tested (`UR_RESULT_ERROR_OUT_OF_RESOURCES`, even at 100 nodes). If a PyG baseline such as HGCN is ever added, it runs on CPU only. |
| Benchmark first | Before training, run one forward and backward pass at batch 256 on XPU and on CPU. Record the time per step and peak memory in `docs/VALIDATION_LOG.md`, and fall back to CPU if XPU errors. |
| Model size | [P] used `d_h = 256`, `L = 4`, 8 heads, roughly 8–9M parameters by a rough `32·d_h²·L` estimate. That is too slow for laptop training. **Recommended:** `d_h = 128`, `L = 3`, 8 heads (≈ 1.7M, XPU). **Small fallback:** `d_h = 64`, `L = 2`, 4 heads (≈ 0.3M; time both devices). Confirm counts with `sum(p.numel() for p in model.parameters())`. |
| Training budget | ≤ 3 h wall-clock, batch 256–512, `W = min(10, feasible first actions)`, Adam lr 2e-4, one EMA warm-up epoch. Instances are generated on the fly from `nco-train` seeds, with a checkpoint every N steps. The 15.4 GB of RAM is shared with development work, so cap the batch size if it swaps. |
| Recorded inference | CPU, `torch.use_deterministic_algorithms(True)`, fixed thread count. Instances are tiny, so inference cost is negligible. |
| NPU | Optional, **inference only**, through OpenVINO with **fixed input shapes**. That means padding to `(T_max, A_max)` and exporting the encoder only. The decoder is autoregressive with dynamic masks, a poor fit for the NPU. Not on any gate. |

## 7. Decisions taken and deferred questions

Resolved by the team on 2026-11-14:

1. **Scope:** the neural allocator is **not** in the hackathon MVP. It is a deferred, optional, local-only comparison baseline, so no exception to §2.2 is needed (D022, D028).
2. **Allocator for Experiments A–C:** **CP-SAT**, with the greedy fallback disclosed (D029). The neural baseline appears only in the optional Experiment E.

Deferred until the baseline work starts (none of these blocks the hackathon):

3. **Decoder order.** Task → agent is recommended, because precedence makes tasks the natural "next location". The alternative is agent → task.
4. **Scale sweep.** Should Experiment E go beyond the brief's mission sizes (for example 8/16/32 tasks)? [P] predicts no quality advantage at small sizes, so without a larger size Experiment E can only show parity and speed.
5. **When and who.** When does the local training run (about 3 h on the XPU) happen, and who watches it?
6. **Reuse of the authors' MIT code.** Adapt `rl4msprp` encoder and decoder modules with attribution, or write them from the paper? Adapting is faster but needs a licence notice, and it pulls in `hydra` and `neptune` if copied wholesale.
7. **Fine-tuning from executed missions.** Default: never. If wanted later, the proposal is "only `ADMITTED` episodes, canonical reward only", which needs a new decision.
8. **Allocator poisoning experiment.** Should there be a "poisoned training data" attack demonstration? Default: no, it stays out of scope. INV-10 prevents the attack path rather than measuring it.
9. **Topology as input.** Train one model across all three topologies and the low/base/high `h0`/`h1` settings (recommended, so sensitivity checks stay in-distribution), or train one model per topology?

## Sources (actually read)

- Luttmann & Xie (2024), full text (9 pages), read from the Internet Archive copy of the ICAPS open-access PDF: <https://web.archive.org/web/20250614164946/https://ojs.aaai.org/index.php/ICAPS/article/download/31494/33654>. The live page <https://ojs.aaai.org/index.php/ICAPS/article/view/31494> refused automated access (bot protection).
- Semantic Scholar record (metadata and abstract; confirms the DOI and that there is no arXiv ID): <https://api.semanticscholar.org/graph/v1/paper/DOI:10.1609/icaps.v34i1.31494?fields=title,externalIds,openAccessPdf,url,abstract>
- arXiv API author query, showing no arXiv entry for the ICAPS paper: <https://export.arxiv.org/api/query?search_query=au:Luttmann&max_results=30>
- Official code: README, `setup.py`, and imports of `rl4mixed/models/encoder/{comb_encoder,han_encoder,het_gcn}.py`: <https://github.com/LTluttmann/rl4msprp>
- Follow-up paper (abstract page only): <https://arxiv.org/abs/2502.10233>
