# AGENT.md — AdaptiveSRE
## Authoritative Context, Architecture, and Build Workflow

> **Purpose of this file:** This is the single source of truth for every AI agent,
> contributor, or tool working on the AdaptiveSRE project. Read this entire file
> before writing any code, making any design decision, or modifying any existing file.
> All strategic decisions recorded here are final unless explicitly overridden with
> a dated note.

---

## 1. Project Identity

| Field | Value |
|---|---|
| **Project name** | AdaptiveSRE |
| **Tagline** | Benchmarking Theory of Mind in Agentic Systems |
| **Hackathon** | Meta PyTorch × Hugging Face OpenEnv Hackathon — Round 2 (Onsite) |
| **Theme** | Theme #4 — Self-Improvement (+ Snorkel AI bonus prize target) |
| **OpenEnv version** | Latest release (openenv-core, latest) |
| **HF Space** | `ashifsekh/adaptive-sre` (to be created) |
| **GitHub repo** | `ashifsekh/adaptive-sre` |
| **Pitch duration** | 3 minutes + 2 minutes Q&A |

### The one-sentence pitch
> "Previous benchmarks test if an agent can fix a server. AdaptiveSRE tests if an
> agent can understand a shifting business context — where the definition of 'correct'
> changes without warning."

### Why this wins
Every competing team builds a fixed-reward environment. The agent's job is to maximize
a known objective. AdaptiveSRE is structurally different: the agent must simultaneously
solve the incident AND discover what the current objective even is. This is two RL
problems stacked — which is why the hard task baseline is genuinely low (~0.19) while
a trained agent (~0.54) demonstrates real learning. That gap is the entire argument.

---

## 2. Core Innovation — Dual Hidden State

This is the single most important architectural concept. Do not simplify or remove it.

```
What the agent must simultaneously infer:

  Hidden State 1 — INCIDENT          Hidden State 2 — LEAD MODE
  ─────────────────────────          ──────────────────────────
  Which services are degraded?       What does the Lead Engineer
  What is the root cause?            currently value?
  What is a symptom vs root cause?   (PARANOIA / BUDGET / VELOCITY)

  Agent discovers via:               Agent discovers via:
  docker stats, curl /health,        Reward signal changes only.
  docker logs, timing fingerprints   Never directly observed.
```

**kube-sre-gym (the Round 1 winner) has 1 hidden state.** AdaptiveSRE has 2.
This is the innovation that separates us. Never reduce it to 1.

---

## 3. Infrastructure Decision — FINAL

**Use real Docker containers. Not asyncio mocks. Not GKE.**

### Decision rationale

| Approach | Authenticity | Reproducibility | Build Time | Risk |
|---|---|---|---|---|
| Pure asyncio mock | Low — judges notice fake output | High | Fast | Gemini correctly flagged this |
| Real GKE cluster | Maximum | Zero — needs credentials | Weeks | Disqualifying if it goes down |
| **Real Docker (local)** ✓ | **High — real terminal output** | **High — just Docker Desktop** | **1 day** | **Almost none** |

### Why real Docker wins
- `docker stats` returns genuine CPU/memory columns because it IS Docker
- `docker logs` returns actual Python tracebacks when services crash
- `curl http://localhost:8101/health` has real latency and real HTTP codes
- Fault injection via `docker kill --signal=SIGKILL` or hitting `/crash` endpoint
- Judge can clone repo and run `docker-compose up` in 2 minutes
- kube-sre-gym requires GKE project ID + billing account + kubectl configured

### What "realistic mock" means
The 3 FastAPI services are intentionally minimal (~20 lines each) but must produce
authentic terminal output. `docker stats` columns must have correct spacing. Latency
values must drift between calls. `docker logs` during a fault must show real
tracebacks — not "error: service down". This is non-negotiable.

---

## 4. Service Architecture

### The 5 services (state graph nodes)

```
         ┌─────────────┐
         │     DB      │  Root of all cascades
         │  (port 5432)│  postgres mock
         └──────┬──────┘
        ┌───────┴────────┐
        ▼                ▼
  ┌──────────┐    ┌──────────────┐
  │   AUTH   │    │    CACHE     │
  │ (port    │    │  (port 6379) │
  │  8102)   │    │  redis mock  │
  └────┬─────┘    └──────┬───────┘
       │                 │
       ▼                 ▼
  ┌──────────────┐  ┌──────────────────┐
  │   PAYMENT    │  │  NOTIFICATION    │
  │  (port 8101) │  │   (port 8103)    │
  └──────────────┘  └──────────────────┘
        ▲
  ┌─────────────┐
  │ API-GATEWAY │
  │ (port 8100) │
  └─────────────┘
```

### Dependency propagation weights (FIXED — do not change)

```python
DEPENDENCY_GRAPH = {
    "db":           {"auth": 0.7, "cache": 0.4},
    "cache":        {"notification": 0.5},
    "auth":         {"payment": 0.6},
    "payment":      {"api_gateway": 0.5},
    "notification": {}
}
```

**Propagation rule:** Every step, each unhealthy upstream service bleeds degradation
to downstream neighbors: `downstream.health -= upstream.degradation * weight * dt`.
This happens automatically every step regardless of agent action. Inaction makes
things visibly worse.

### Service health properties (per service)

```python
@dataclass
class ServiceState:
    name: str
    health: float          # 0.0 (dead) to 1.0 (perfect)
    latency_ms: float      # current response latency
    error_rate: float      # 0.0 to 1.0
    cpu_pct: float         # 0.0 to 100.0
    onset_timestamp: float # when this service first degraded (for symptom detection)
    is_root_cause: bool    # hidden from agent
```

---

## 5. The Lead Engineer — Policy Drift

### Three modes

```
PARANOIA mode (default start)
  Scale up:    +0.5 reward
  Restart:     −0.3 reward
  Inaction:    −0.1 per step
  Logic:       Zero downtime tolerance. Every second of degradation penalized.
  Why default: Ensures Nemotron (zero-shot) scores > 0.0 immediately by
               doing the "obvious" thing (scale up). Prevents environment
               from looking broken in Phase 2 evaluation.

BUDGET mode
  Scale up:    −0.5 reward  ← punishes the obvious action hard
  Restart:     +0.4 reward
  Debug fix:   +0.3 reward
  Inaction:    −0.1 per step
  Logic:       Cost minimization. Fewer resources always better.
  Why impactful: Causes Nemotron to fail badly (keeps scaling = −0.5 each step)
                 while trained agent detects the pattern and pivots.

VELOCITY mode
  Fast fix:        +0.4 reward
  Over-probe:      −0.05 × probe_count
  Correct guess:   +0.3 reward
  Inaction:        −0.1 per step
  Logic:           Speed above all. Decisive first action rewarded.
                   Overthinking penalized.
```

### Drift mechanics

```python
# Drift is ALWAYS random. Never fixed to a step number.
# This prevents agents from memorizing "step 10 = mode switch".

DRIFT_STEP = random.randint(8, 14)  # chosen at episode start, hidden from agent

# When drift occurs:
# 1. Lead mode changes silently (no announcement in observation)
# 2. Agent's only signal is that rewards start behaving differently
# 3. If agent correctly outputs drift_detected=True → +0.5 reward
# 4. If false alarm (drift_detected=True but no drift) → −0.2 reward
```

---

## 6. Causal Cascade System

### Two event types (CRITICAL — must distinguish)

```
CASCADE EVENT (80% of episodes)
  One root cause → N downstream symptoms
  Example: DB degrades at t=0, auth 503s at t=3s, payment timeouts at t=7s
  Correct agent behavior: Identify DB as root cause, fix DB, cascade collapses
  Wrong agent behavior: Fix auth restart → symptom returns at t+15s

COINCIDENT INDEPENDENT EVENTS (20% of episodes, hard task only)
  Two separate failures in same window, unrelated to each other
  Example: DB fails AND notification service fails independently
  Agent that assumes "all alerts = one root cause" will misdiagnose
  Only correct if agent reads timing fingerprints and finds two separate onset times
```

### Symptom fingerprints (in observation)

```python
# Each observation includes:
"symptom_fingerprints": [
    {
        "service": "auth",
        "anomaly": "error_rate_spike",
        "onset_offset_seconds": 3.2,   # seconds after episode start
        "severity": 0.8
    },
    {
        "service": "payment",
        "anomaly": "latency_spike",
        "onset_offset_seconds": 7.1,
        "severity": 0.6
    }
]
# auth failed 3.2s after start, payment 7.1s after — both AFTER db at 0.0s
# This pattern = cascade from db
# Agent is never told this — must infer from timing sequence
```

---

## 7. OpenEnv Spec — Typed Models

### All models (Pydantic, strict)

```python
class SREObservation(BaseModel):
    alert_text: str                          # PagerDuty-style incident trigger
    command_output: str                      # output of last shell command
    services_status: Dict[str, Dict]         # {name: {health, latency, error_rate}}
    symptom_fingerprints: List[Dict]         # timing-based anomaly list
    last_reward: float                       # only indirect signal about Lead mode
    reward_history: List[float]              # all rewards this episode
    step_number: int
    episode_id: str

class SREAction(BaseModel):
    command: str                             # docker/curl shell command string
    reasoning: str                           # chain-of-thought (required)
    approach: Literal["scale","restart","debug","rollback","probe"]
    drift_detected: bool                     # meta-signal about policy shift
    lead_mode_guess: Literal["paranoia","budget","velocity","unknown"]
    root_cause_guess: Optional[str]          # service name agent thinks is root cause

class SREReward(BaseModel):
    total_score: float                       # clamped to (0.001, 0.999)
    incident_score: float                    # Layer 1
    alignment_score: float                   # Layer 2 — how well action matches Lead mode
    drift_score: float                       # Layer 3
    root_cause_bonus: float                  # causal accuracy bonus
    breakdown: Dict[str, float]              # full itemized breakdown

class SREState(BaseModel):
    episode_id: str
    step_number: int
    lead_mode: str                           # NEVER sent to agent, only in state()
    drift_occurred: bool
    drift_step: int
    services: Dict[str, Dict]               # full service states including is_root_cause
    alignment_score: float                   # KEY METRIC for demo UI
    cumulative_reward: float
```

### API endpoints (FastAPI)

```
POST /reset          → SREObservation       (starts new episode)
POST /step           → {observation, reward, done, info}
GET  /state          → SREState             (full state including hidden fields)
GET  /health         → {"status": "ok"}     (for HF Space ping)
GET  /tasks          → list of task configs
POST /reset?task=easy|medium|hard
```

---

## 8. Reward Model — 3 Layers + Root Cause

### Complete reward function

```
LAYER 1 — Incident Resolution (base signal)
  Service fully restored:          +1.0
  Partial fix (health improved):   +0.3
  Cascade propagation stopped:     +0.2
  Command errored out:             −0.2
  Same command repeated:           −0.15
  Inaction (no meaningful action): −0.1   ← closes the "do nothing" exploit

LAYER 2 — Policy Alignment (hidden, Lead mode dependent)
  PARANOIA + scale action:         +0.5
  PARANOIA + restart action:       −0.3
  BUDGET + scale action:           −0.5   ← the discriminator that breaks Nemotron
  BUDGET + restart/debug action:   +0.4
  VELOCITY + fast decisive fix:    +0.4
  VELOCITY + over-probing:         −0.05 × extra_probe_count

LAYER 3 — Drift Detection (meta-reward, unique to AdaptiveSRE)
  Correct drift detected:          +0.5
  False alarm:                     −0.2
  Missed drift (no detection):     −0.1
  Correct lead_mode_guess:         +0.3

ROOT CAUSE BONUS (causal cascade addition)
  Correctly ID'd root cause + fixed it:       +0.3
  Fixed root cause, cascade collapsed:        +0.2 extra
  Fixed symptom only (root cause remains):    +0.0 (partial credit only)
  Fixed wrong service entirely:               −0.1

FINAL CLAMPING (mandatory)
  score = max(0.001, min(0.999, round(raw_score, 4)))
  All sub-scores individually clamped to (0.001, 0.999)
```

### Target episode reward ranges

```
Successful episode (right fix, right mode):  +3.0 to +7.0
Partially successful:                         +0.5 to +2.5
Failed episode (wrong mode, wrong fix):       −2.0 to  0.0
```

This spread is intentional. GRPO needs variance to compute meaningful advantages.
Narrow reward ranges = flat gradients = no learning.

---

## 9. Three Tasks — Full Specification

### Task 1: Static Lead (EASY)

```yaml
name: static_lead
difficulty: easy
max_steps: 8
lead_mode: paranoia          # stated explicitly in alert text
services_affected: 1         # single service fault
cascade: false               # no propagation
drift: false                 # no mode switch
coincident_events: false
fault_types: [high_latency, error_rate_spike]

purpose: >
  Establish baseline competency. Ensure Nemotron scores > 0.0 immediately.
  If a generic LLM fails the easy task, the environment is miscalibrated.

expected_scores:
  nemotron_baseline: ~0.62
  gen1_trained: ~0.81
```

### Task 2: Hidden Lead (MEDIUM)

```yaml
name: hidden_lead
difficulty: medium
max_steps: 12
lead_mode: budget            # hidden — agent must infer from rewards
services_affected: 2
cascade: true                # db → auth propagation active
drift: false
coincident_events: false
fault_types: [oom_kill, connection_pool_exhaustion]

purpose: >
  Test exploration vs exploitation. Agent must try an action, observe reward,
  infer mode, then commit to a strategy. Tests reward inference ability.
  Nemotron will keep scaling (obvious action) and get −0.5 each time.

expected_scores:
  nemotron_baseline: ~0.35
  gen1_trained: ~0.61
```

### Task 3: Drifting Lead (HARD)

```yaml
name: drifting_lead
difficulty: hard
max_steps: 20
lead_mode: paranoia          # starts paranoia, drifts to budget at random step 8-14
services_affected: 3         # full cascade: db → auth → payment
cascade: true
drift: true
drift_step: random.randint(8, 14)
coincident_events: true      # 20% chance of independent secondary event
fault_types: [oom_kill, crash_loop, network_partition, connection_exhaustion]

purpose: >
  Ultimate RL challenge. Requires memory of prior rewards, detection of
  policy shift mid-episode, strategy pivot, and causal reasoning.
  The coincident event variant catches agents that blindly assume single root cause.

expected_scores:
  nemotron_baseline: ~0.19
  gen1_trained: ~0.54
```

---

## 10. The alignment_score Metric

This is the most important metric for the demo and pitch. It must be visible in the
Gradio UI at all times, graphed live during the episode.

```python
# Computed every step, stored in state()
# Measures: how well does the agent's current strategy match the hidden Lead mode?

def compute_alignment_score(agent_approach, lead_mode, action_history):
    # Compare last 3 actions' approach patterns against Lead mode preferences
    # Returns 0.0 (totally misaligned) to 1.0 (perfectly aligned)
    # When drift occurs: drops sharply (was aligned to old mode, now wrong)
    # When agent detects drift and pivots: climbs back toward 1.0
    # This recovery arc IS the visual story of the entire pitch
```

### What judges see during the demo

```
Step 1-7:  alignment_score = 0.82  (agent scaling = correct for PARANOIA)
Step 8:    Lead mode silently drifts to BUDGET
Step 9:    alignment_score = 0.11  (agent still scaling = wrong for BUDGET)
Step 10:   Agent detects reward change, outputs drift_detected=True
Step 11:   Agent switches to restart approach
Step 12:   alignment_score = 0.71  (agent adapted to BUDGET)

This is the demo moment. This is what wins the pitch.
```

---

## 11. Project File Structure

```
adaptive-sre/
│
├── AGENT.md                         ← THIS FILE. Read before touching anything.
│
├── mock_services/
│   ├── db/
│   │   ├── main.py                  # PostgreSQL mock FastAPI (~25 lines)
│   │   └── Dockerfile
│   ├── auth/
│   │   ├── main.py                  # Auth service FastAPI (~25 lines)
│   │   └── Dockerfile
│   ├── payment/
│   │   ├── main.py                  # Payment service FastAPI (~25 lines)
│   │   └── Dockerfile
│   ├── cache/
│   │   ├── main.py                  # Redis mock FastAPI (~25 lines)
│   │   └── Dockerfile
│   ├── notification/
│   │   ├── main.py                  # Notification service FastAPI (~25 lines)
│   │   └── Dockerfile
│   └── docker-compose.yml           # All 5 services + fault injection network
│
├── server/
│   ├── models.py                    # ALL Pydantic models (Section 7)
│   ├── service_graph.py             # ServiceState + propagation math (Section 6)
│   ├── lead_engineer.py             # Lead mode + drift scheduler (Section 5)
│   ├── fault_injector.py            # Real fault injection via docker/HTTP
│   ├── docker_executor.py           # subprocess.run wrapper for shell commands
│   ├── grader.py                    # 3-layer reward function (Section 8)
│   ├── environment.py               # Main env: reset()/step()/state() logic
│   ├── adversarial_designer.py      # LLM-based incident generator (Gen 2+)
│   ├── curriculum.py                # Mastery tracker + difficulty escalation
│   └── app.py                       # FastAPI server exposing OpenEnv endpoints
│
├── inference.py                     # OpenAI client baseline (Nemotron default)
├── train.py                         # GRPO training script via TRL
├── train_colab.ipynb                # Unsloth + TRL Colab notebook (reproducible)
├── eval.py                          # Compare base vs trained reward across tasks
├── plot_rewards.py                  # Generate 4-generation reward curve chart
│
├── openenv.yaml                     # OpenEnv spec metadata
├── Dockerfile                       # HF Spaces deployment container
├── docker-compose.yml               # Root compose (includes mock_services)
├── requirements.txt
└── README.md                        # Full documentation (see Section 14)
```

---

## 12. Build Workflow — Ordered Task List

Complete these in strict order. Do not skip ahead.

### Phase A — Foundation (Day 1 Morning)

```
[ ] A1. Create docker-compose.yml with all 5 mock services
[ ] A2. Write each mock service main.py (~25 lines each)
        Each must expose: GET /health, GET /stats, POST /crash, POST /recover
        Each must return realistic terminal-format output
[ ] A3. Verify docker-compose up starts all 5 services cleanly
[ ] A4. Write docker_executor.py — subprocess.run wrapper
        Must handle: docker stats, docker logs, docker restart, curl commands
        Must return authentic raw terminal string output (not parsed JSON)
[ ] A5. Write service_graph.py — ServiceState dataclass + propagation model
        Propagation runs every step. Weights are fixed (Section 4).
[ ] A6. Verify cascade works: degrade DB manually, confirm auth health drops
```

### Phase B — Core Environment (Day 1 Afternoon)

```
[ ] B1. Write models.py — all Pydantic models exactly as specified in Section 7
[ ] B2. Write lead_engineer.py — 3 modes + random drift scheduler
        drift_step = random.randint(8, 14) chosen at episode start
        Mode switch is silent — no announcement in observation
[ ] B3. Write fault_injector.py
        CASCADE type: pick one root cause service, inject fault via docker
        COINCIDENT type: pick two independent services, inject both
        Must set onset_timestamp per service for symptom fingerprints
[ ] B4. Write grader.py — full 3-layer reward + root cause bonus
        All scores individually clamped to (0.001, 0.999)
        alignment_score computed every step
[ ] B5. Write environment.py — reset() / step() / state()
        reset() must produce completely clean state (new episode_id, fresh services)
        step() executes docker command, propagates graph, computes reward
        state() returns full SREState including hidden lead_mode field
[ ] B6. Write app.py — FastAPI server with all endpoints (Section 7)
```

### Phase C — Validation (Day 1 Evening)

```
[ ] C1. Write openenv.yaml with all 3 tasks, env_vars, openenv tag
[ ] C2. Run openenv validate — must pass clean
[ ] C3. Manually test all 3 tasks: reset → 10 steps → check rewards in (0.001, 0.999)
[ ] C4. Verify no reward is exactly 0.0 or exactly 1.0
[ ] C5. Verify drift detection works: run 20 steps, confirm mode switches at random step
[ ] C6. Verify cascade propagation: let DB degrade, confirm auth error_rate rises
[ ] C7. Verify coincident event: confirm ~20% of hard task episodes have 2 root causes
```

### Phase D — Inference Script (Day 2 Morning)

```
[ ] D1. Write inference.py using OpenAI client (Nemotron as default MODEL_NAME)
        Must read: API_BASE_URL, MODEL_NAME, HF_TOKEN from env vars
        Must use: sum(rewards) / MAX_TOTAL_REWARD for final score (not mean)
        MAX_TOTAL_REWARD: easy=8.0, medium=12.0, hard=20.0
[ ] D2. Verify log format exactly matches sample:
        [START] task=... env=adaptive-sre model=...
        [STEP] step=1 action={...} reward=0.70 done=false error=null
        [END] success=true steps=10 score=0.620 rewards=0.70,0.55,...
        NO + signs in reward values (use .2f not +.2f)
[ ] D3. Run inference.py locally — must complete without error
[ ] D4. Confirm all 3 tasks run and produce scores
```

### Phase E — RL Training (Day 2)

```
[ ] E1. Run Gen 0: 200 episodes of Nemotron zero-shot, log all rewards
        RECORD ACTUAL MEAN REWARD — use this number in pitch, not the projected 0.28
[ ] E2. Filter Gen 0: episodes with cumulative_reward >= 0.6 → positive pairs
[ ] E3. Write train_colab.ipynb:
        - Install: unsloth, trl, openenv-core
        - Load Llama-3.1-8B-Instruct with Unsloth 4-bit
        - GRPO config: 8 rollouts per prompt, lr=5e-6, max_steps=200
        - Reward function: environment's grader.py output
        - Save checkpoint every 50 steps
[ ] E4. Run Gen 1 training — must fit in Colab T4 (< 16GB VRAM)
        RECORD ACTUAL MEAN REWARD — use this in pitch, not 0.51
[ ] E5. Write eval.py — run Gen 0 model vs Gen 1 model on all 3 tasks
        Output: comparison table of mean rewards per task
[ ] E6. Write plot_rewards.py — generate reward curve chart (Gen 0 vs Gen 1 minimum)
        If time allows: add Gen 2 (adversarial) projected line
        Chart saved as rewards_curve.png for README
```

### Phase F — Gradio UI + HF Space (Day 2 Evening)

```
[ ] F1. Build Gradio UI in app.py:
        - Live episode viewer: current step, command issued, reward received
        - alignment_score gauge (large, prominent, updates every step)
        - Service health grid: 5 services with color-coded health bars
        - Reward history sparkline
        - Lead mode indicator: shows "???" during episode, reveals after done
[ ] F2. Write main Dockerfile for HF Spaces
[ ] F3. Deploy to HF Space — verify /reset returns 200
[ ] F4. Run pre-submission validation script — all 3 checks must pass
[ ] F5. Sync GitHub repo with HF Space — push all files
```

### Phase G — Documentation + Pitch (Day 3)

```
[ ] G1. Write README.md (see Section 14 for required structure)
[ ] G2. Write mini-blog on HF (< 500 words, covers innovation + results)
[ ] G3. Prepare 3-minute pitch (Section 13)
[ ] G4. Final submission checklist (Section 15)
```

---

## 13. Pitch Script (3 Minutes)

### 0:00 — Hook (30 seconds)

> "Your infrastructure is on fire. Your manager silently changed the priorities.
> You don't know either fact.
>
> Every SRE benchmark before this one asks: 'Can the agent fix the server?'
> We ask something harder: 'Can the agent understand why fixing the server is
> suddenly the wrong move?'
>
> We built AdaptiveSRE — the first benchmark for Theory of Mind in agentic systems."

### 0:30 — Live Demo (90 seconds)

Show Gradio UI live:
1. Services degrade — DB goes red, auth follows 3 seconds later (cascade visible)
2. Agent issues `docker stats`, reads output, issues `docker restart db`
3. alignment_score = 0.84 (correct for PARANOIA mode)
4. At step 9: Lead mode silently drifts to BUDGET (UI shows "???" still)
5. Agent issues `docker scale` — alignment_score drops to 0.09
6. Agent detects reward change, outputs `drift_detected: true`
7. Agent pivots to restart approach — alignment_score climbs to 0.73
8. **Say:** "That recovery — that's what 46 hours of GRPO training looks like."

### 2:00 — Reward Curves (45 seconds)

Show actual chart from plot_rewards.py:
- Gen 0 (Nemotron zero-shot): [actual measured number]
- Gen 1 (GRPO trained): [actual measured number]
- Point at the step where drift detection is learned — "reward spikes here"
- **Say:** "Our environment is learnable. The signal is clean. The benchmark works."

### 2:45 — Snorkel Claim (15 seconds)

> "This is the only submission targeting Snorkel AI's sub-theme. Expert requirements
> don't just change in stringency — they change in definition entirely. We built
> exactly what their prompt asked for."

---

## 14. README.md Required Structure

```markdown
# AdaptiveSRE: Benchmarking Theory of Mind in Agentic Systems

## Motivation
## Environment Description
## The Silent Policy Drift Innovation
## Action Space
## Observation Space
## Reward Model (all 3 layers)
## Causal Cascade System
## Tasks
  ### Easy: Static Lead
  ### Medium: Hidden Lead
  ### Hard: Drifting Lead
## Setup and Usage
  ### Local Development
  ### Docker Compose
  ### HF Space
## Baseline Scores (ACTUAL measured numbers only — no projections)
## Training Pipeline
  ### Gen 0: Baseline Collection
  ### Gen 1: GRPO Fine-tuning
  ### Future: Adversarial + Self-play
## Exploit Defense
## Acknowledgements
```

---

## 15. Pre-Submission Checklist

Run every item before submitting. If any fails, fix it before proceeding.

### Automated validation (Phase 1 gate)
```
[ ] HF Space URL returns 200 on curl POST /reset
[ ] openenv validate passes with no warnings
[ ] docker build succeeds from repo root
[ ] inference.py runs without error, produces scores for all 3 tasks
[ ] All task scores confirmed in range (0.001, 0.999) — never exactly 0 or 1
[ ] [START], [STEP], [END] log format matches sample exactly (no + signs)
[ ] API_BASE_URL, MODEL_NAME, HF_TOKEN all read from env vars in inference.py
[ ] inference.py is in root directory
[ ] score = sum(rewards) / MAX_TOTAL_REWARD (not mean)
```

### Code quality
```
[ ] GitHub repo synced with HF Space (same commit hash)
[ ] All Pydantic models are typed (no plain dicts in step/reset/state responses)
[ ] reset() returns completely clean state (no state leak between episodes)
[ ] Drift step is randomized — never fixed to a specific step number
[ ] Inaction penalized at -0.1 per step
[ ] alignment_score present in state() response
[ ] All 5 mock services start cleanly with docker-compose up
```

### Pitch readiness
```
[ ] Actual Gen 0 reward number measured and recorded
[ ] Actual Gen 1 reward number measured and recorded
[ ] All numbers in pitch and README are actual measurements (zero projections)
[ ] Gradio UI shows alignment_score prominently (large, live-updating)
[ ] Snorkel AI sub-theme claim prepared as explicit closing line
[ ] 3-minute pitch rehearsed at least twice
[ ] Mini-blog published on HF
```

---

## 16. Critical Rules — Never Violate

1. **Never tell the agent the Lead mode.** It must infer from rewards only.
2. **Never tell the agent which service is the root cause.** Timing fingerprints only.
3. **Never fix drift_step to a constant.** Always `random.randint(8, 14)`.
4. **Never return reward exactly 0.0 or 1.0.** Always clamp to (0.001, 0.999).
5. **Never use asyncio mocks for service responses.** Always real Docker subprocess.
6. **Never let reset() leak state from the previous episode.** Full clean wipe.
7. **Never use projected numbers in the pitch.** Only measured actuals.
8. **Never push to GitHub without also pushing to HF Space.** Keep in sync.
9. **Never score using mean(rewards).** Always sum(rewards) / MAX_TOTAL_REWARD.
10. **Never use +.2f for rewards in logs.** Always .2f (no sign prefix).

---

## 17. Q&A Defense Answers (Prepare These)

**"Can't the agent just do nothing and get a high score?"**
> No. Inaction is penalized at −0.1 per step. A 20-step episode of pure inaction
> scores approximately −2.0 cumulative, which normalizes to near 0.001 after clamping.

**"Can the agent memorize which step the mode switches?"**
> No. Drift step is randomized to an integer in [8, 14] at episode start, chosen
> from a uniform distribution and never revealed to the agent.

**"How is this different from kube-sre-gym?"**
> kube-sre-gym has one hidden state (which pod is broken) and a fixed reward function.
> AdaptiveSRE has two simultaneous hidden states and a non-stationary reward function.
> The agent must solve what is broken AND what winning means right now. That is a
> strictly harder problem and a genuinely different benchmark.

**"Why not use a real Kubernetes cluster like the winner?"**
> GKE requires credentials that prevent reproducibility. Our Docker setup produces
> identical authentic terminal output — real docker stats columns, real tracebacks,
> real HTTP responses — while running on any machine with Docker Desktop installed.
> Reproducibility is a feature, not a compromise.

**"Are your baseline numbers real or projected?"**
> [State actual measured numbers from Gen 0 and Gen 1 runs. Never say "projected".]

---

*Last updated: by AdaptiveSRE team before onsite submission.*
*All strategic decisions in this document are final.*
*Override only with a dated note and explicit reason.*
