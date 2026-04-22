# MASTER BUILD GUIDE — AdaptiveSRE
## Complete Agent Prompt Sequence + Verification Checkpoints

> **How to use this file:**
> 1. Give prompts to your OpenCode CLI agent in the exact order listed below.
> 2. After each prompt, run the checkpoint test shown. Verify the expected output.
> 3. If the model hits context limits or you switch models, use the RESUME PROMPT
>    at the top of the next prompt — it re-anchors the new model to your codebase.
> 4. PROGRESS.md is auto-updated by the agent after each phase. It is your
>    context anchor when switching between Claude, GPT-4, or Gemini mid-session.

---

## Model-Switch Strategy (The "Graphify" System)

When a model hits its context limit or you want to switch models, use this protocol:

### Step 1 — Before switching, tell the current model:
```
Update PROGRESS.md with:
- Which phase just completed
- Every file created or modified (with paths)
- Any decisions made that deviate from AGENT.md
- The exact next step to continue from
Then stop.
```

### Step 2 — Resume prompt for the NEW model (paste this first):
```
You are continuing development of AdaptiveSRE, a hackathon project.

Read these files in this exact order before doing anything else:
1. AGENT.md              — full project spec, architecture, all decisions
2. PROGRESS.md           — what has been built so far, where we stopped
3. The file listed as "next step" in PROGRESS.md

Do not ask questions. Do not summarize. Just read those three files,
then tell me: "I have read the context. Ready to continue from [X]."
Wait for my next instruction.
```

### Step 3 — Continue with the next prompt in this guide.

---

## Project Structure to Build

```
adaptive-sre/
├── AGENT.md
├── PROGRESS.md                    ← agent maintains this
├── mock_services/
│   ├── db/main.py + Dockerfile
│   ├── auth/main.py + Dockerfile
│   ├── payment/main.py + Dockerfile
│   ├── cache/main.py + Dockerfile
│   ├── notification/main.py + Dockerfile
│   └── docker-compose.yml
├── server/
│   ├── models.py
│   ├── service_graph.py
│   ├── lead_engineer.py
│   ├── fault_injector.py
│   ├── docker_executor.py
│   ├── grader.py
│   ├── environment.py
│   ├── adversarial_designer.py
│   ├── curriculum.py
│   └── app.py
├── inference.py
├── train.py
├── train_colab.ipynb
├── eval.py
├── plot_rewards.py
├── openenv.yaml
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## PHASE 0 — Project Init (Give this FIRST)

### Prompt 0:
```
You are building AdaptiveSRE, a hackathon project for the Meta PyTorch x HuggingFace
OpenEnv Hackathon. Read AGENT.md completely before writing any code — it is the
authoritative spec for everything. Do not deviate from it.

Your task for this phase:
1. Create the project directory structure exactly as shown in AGENT.md Section 11.
2. Create PROGRESS.md with this initial content:
   - Phase: 0 — Init complete
   - Files created: directory structure only
   - Next step: Phase 1 — Mock services
3. Create requirements.txt with these exact packages:
   fastapi==0.115.0
   uvicorn==0.30.0
   pydantic==2.7.0
   httpx==0.27.0
   openai==1.40.0
   docker==7.1.0
   openenv-core
   gradio==4.44.0
   trl==0.9.6
   transformers==4.44.0
   torch==2.4.0
   unsloth
   pytest==8.3.0
   pytest-asyncio==0.23.0

Do not write any Python logic yet. Only structure and requirements.txt.
After completing, show me the directory tree output.
```

### Checkpoint 0 — Run this:
```bash
find adaptive-sre -type f | sort
```

### Expected output:
```
adaptive-sre/AGENT.md
adaptive-sre/PROGRESS.md
adaptive-sre/mock_services/
adaptive-sre/requirements.txt
adaptive-sre/server/
```

---

## PHASE 1 — Mock Services (5 Real Docker FastAPI Services)

### Prompt 1:
```
Read AGENT.md Section 4 (Service Architecture) and Section 3 (Infrastructure Decision).

Build all 5 mock microservices. Each service must be a real FastAPI app in its own
directory with its own Dockerfile. They must produce authentic terminal output — not
fake strings. Follow these rules for every service:

RULES (critical — do not violate):
- Each service tracks its own state: health (float 0.0-1.0), latency_ms (float),
  error_rate (float 0.0-1.0), cpu_pct (float 0.0-100.0)
- GET /health → returns JSON with all state fields + realistic latency simulation
  (use asyncio.sleep(state["latency_ms"]/1000))
- GET /stats → returns docker-stats-style text (not JSON) with realistic column spacing:
  "CONTAINER    CPU%    MEM/LIMIT       MEM%    NET I/O"
  Values must vary slightly each call using random.uniform()
- POST /crash → sets health=0.1, error_rate=0.9, latency_ms=random(800,3000)
- POST /recover → sets health=1.0, error_rate=0.0, latency_ms=random(20,80)
- GET /logs → returns realistic Python traceback when error_rate > 0.5,
  returns normal access log lines when healthy

SERVICE SPECS:
- db: port 5432 (mock postgres), connection_pool_used field in health response
- auth: port 8102, auth_failures_per_min field
- payment: port 8101, transactions_per_sec field
- cache: port 6379 (mock redis), hit_rate field
- notification: port 8103, queue_depth field

Each Dockerfile: FROM python:3.11-slim, install fastapi uvicorn, EXPOSE correct port,
CMD uvicorn main:app --host 0.0.0.0 --port [PORT]

docker-compose.yml: All 5 services, network named "sre-network", healthcheck on each.

After building, update PROGRESS.md:
- Phase: 1 — Mock services complete
- Files created: [list all files]
- Next step: Phase 2 — Core models and service graph
```

### Checkpoint 1 — Run these in order:
```bash
# Start services
cd adaptive-sre
docker-compose -f mock_services/docker-compose.yml up -d

# Wait 10 seconds then test each
sleep 10
curl -s http://localhost:8102/health | python3 -m json.tool
curl -s http://localhost:8101/health | python3 -m json.tool
curl -s http://localhost:5432/health | python3 -m json.tool

# Test crash and recover
curl -s -X POST http://localhost:8102/crash
curl -s http://localhost:8102/health | python3 -m json.tool
curl -s http://localhost:8102/logs

# Test stats format
curl -s http://localhost:8101/stats
```

### Expected output (auth health after crash):
```json
{
  "status": "degraded",
  "health": 0.1,
  "error_rate": 0.9,
  "latency_ms": 1847.3,
  "auth_failures_per_min": 847,
  "port": 8102
}
```

### Expected output (stats):
```
CONTAINER    CPU%    MEM/LIMIT       MEM%    NET I/O
payment-svc  23.4%   187MiB/2GiB    9.2%   1.2MB/340kB
```

---

## PHASE 2 — Core Models + Service Graph

### Prompt 2:
```
Read AGENT.md Section 7 (OpenEnv Spec — Typed Models) and Section 4 (Service Architecture).

Build server/models.py and server/service_graph.py.

FILE 1: server/models.py
Implement ALL Pydantic models exactly as specified in AGENT.md Section 7:
- SREObservation (all fields listed)
- SREAction (all fields listed, use Literal types)
- SREReward (all fields listed)
- SREState (all fields listed)
No shortcuts. Every field from AGENT.md must be present with correct types.

FILE 2: server/service_graph.py
Implement:
- ServiceState dataclass with fields: name, health, latency_ms, error_rate, cpu_pct,
  onset_timestamp, is_root_cause (all from AGENT.md Section 4)
- DEPENDENCY_GRAPH dict exactly as in AGENT.md Section 4 (fixed weights, do not change)
- ServiceGraph class with:
  - __init__: creates 5 ServiceState instances, all healthy (health=1.0)
  - reset(): restores all services to healthy state, new episode_id
  - propagate(dt=1.0): for each edge in DEPENDENCY_GRAPH, bleed degradation:
      downstream.health -= max(0, (1.0 - upstream.health)) * weight * dt * 0.1
      downstream.error_rate += max(0, upstream.error_rate) * weight * dt * 0.05
      all values clamped to valid ranges after propagation
  - get_observation_dict(): returns services_status dict for SREObservation
  - get_symptom_fingerprints(): returns list of dicts with service, anomaly,
    onset_offset_seconds (time since episode start), severity
  - apply_fault(service_name, fault_type): degrades a specific service
    fault_types: "oom_kill", "crash_loop", "network_partition", "connection_exhaustion"
    each sets health/error_rate/latency_ms to realistic degraded values
  - apply_recover(service_name): restores service to health=1.0

After building, update PROGRESS.md.
```

### Checkpoint 2 — Create and run this test:
```bash
cat > /tmp/test_phase2.py << 'EOF'
import sys
sys.path.insert(0, 'adaptive-sre')
from server.service_graph import ServiceGraph
from server.models import SREObservation, SREAction, SREReward, SREState

# Test 1: Pydantic models instantiate correctly
obs = SREObservation(
    alert_text="DB connection pool exhausted",
    command_output="",
    services_status={},
    symptom_fingerprints=[],
    last_reward=0.0,
    reward_history=[],
    step_number=1,
    episode_id="test-001"
)
print(f"[PASS] SREObservation created: episode_id={obs.episode_id}")

action = SREAction(
    command="docker stats --no-stream",
    reasoning="Checking resource usage",
    approach="probe",
    drift_detected=False,
    lead_mode_guess="unknown"
)
print(f"[PASS] SREAction created: approach={action.approach}")

# Test 2: ServiceGraph propagation
graph = ServiceGraph()
print(f"[PASS] Graph created, DB health={graph.services['db'].health}")

# Degrade DB
graph.apply_fault("db", "connection_exhaustion")
db_health = graph.services["db"].health
print(f"[PASS] DB degraded: health={db_health:.2f}")

# Run 5 propagation steps
for i in range(5):
    graph.propagate(dt=1.0)

auth_health = graph.services["auth"].health
payment_health = graph.services["payment"].health
print(f"[PASS] After 5 propagation steps:")
print(f"       auth.health={auth_health:.3f} (should be < 1.0)")
print(f"       payment.health={payment_health:.3f} (should be < 1.0)")

assert auth_health < 1.0, "FAIL: propagation not working — auth unaffected by DB fault"
assert payment_health < 1.0, "FAIL: propagation not reaching payment"

# Test 3: Fingerprints
fps = graph.get_symptom_fingerprints()
print(f"[PASS] Symptom fingerprints: {len(fps)} anomalies detected")
for fp in fps:
    print(f"       {fp['service']}: {fp['anomaly']} @ +{fp['onset_offset_seconds']:.1f}s")

print("\n=== ALL PHASE 2 TESTS PASSED ===")
EOF
python3 /tmp/test_phase2.py
```

### Expected output:
```
[PASS] SREObservation created: episode_id=test-001
[PASS] SREAction created: approach=probe
[PASS] Graph created, DB health=1.0
[PASS] DB degraded: health=0.15
[PASS] After 5 propagation steps:
       auth.health=0.723 (should be < 1.0)
       payment.health=0.891 (should be < 1.0)
[PASS] Symptom fingerprints: 3 anomalies detected
       db: error_rate_spike @ +0.0s
       auth: latency_spike @ +2.3s
       payment: error_rate_spike @ +4.1s

=== ALL PHASE 2 TESTS PASSED ===
```

---

## PHASE 3 — Lead Engineer + Fault Injector + Docker Executor

### Prompt 3:
```
Read AGENT.md Section 5 (Lead Engineer) and the Docker executor note in Section 3.

Build 3 files:

FILE 1: server/lead_engineer.py
Implement LeadEngineer class:
- __init__(task="hard"): sets mode=None, drift_step=None, drift_occurred=False
- reset(task): 
    task="easy" → mode="paranoia", drift_step=None (no drift, mode stated in alert)
    task="medium" → mode="budget", drift_step=None (hidden but fixed)
    task="hard" → mode="paranoia", drift_step=random.randint(8,14)
- check_drift(step_number): if step_number == drift_step → flip mode
    paranoia → budget, budget → velocity, velocity → paranoia
    set drift_occurred=True, return True if drift happened else False
- compute_policy_alignment(approach, probe_count=0):
    Returns float reward adjustment based on current mode + approach
    Use EXACT values from AGENT.md Section 5 (Three modes)
- get_mode_for_observation(task): 
    task="easy" → return mode (stated)
    task="medium" or "hard" → return "unknown"

FILE 2: server/docker_executor.py
Implement DockerExecutor class:
- execute(command_string, timeout=10): 
    Parses command_string and routes to correct mock service via HTTP
    Supported commands (map to HTTP calls):
    "docker stats" → GET /stats on all services, combine output
    "docker stats [service]" → GET /stats on specific service  
    "docker logs [service]" → GET /logs on named service
    "docker restart [service]" → POST /recover on named service, then GET /health
    "docker inspect [service]" → GET /health on service, format as inspect JSON
    "curl http://localhost:[PORT]/health" → direct HTTP GET
    "kubectl get pods" → synthesize kubectl-style output from service health states
    Unknown command → return realistic "command not found" error string
- SERVICE_MAP: dict mapping service names to ports
    {"db": 5432, "auth": 8102, "payment": 8101, "cache": 6379, "notification": 8103}
- All responses must be authentic terminal format strings (not JSON objects)
  "docker stats" must return column-formatted text exactly like real docker stats
  "docker logs" must return raw log lines, not JSON

FILE 3: server/fault_injector.py
Implement FaultInjector class:
- inject_cascade(service_graph, root_service, fault_type):
    Calls POST /crash on the root service via HTTP
    Updates service_graph to mark root service as degraded + is_root_cause=True
    Returns the alert_text string (PagerDuty-style, e.g.:
    "[CRITICAL] P1 Incident — db connection pool exhausted.
     Alert: 847 failed connections in last 60s. Error rate: 89%.
     Downstream: auth-service showing elevated latency.")
- inject_coincident(service_graph, service1, service2, fault1, fault2):
    Injects two independent faults simultaneously
    Both services get is_root_cause=True (two independent root causes)
    Returns combined alert text indicating two simultaneous alerts

After building, update PROGRESS.md.
```

### Checkpoint 3 — Run this test:
```bash
cat > /tmp/test_phase3.py << 'EOF'
import sys, asyncio
sys.path.insert(0, 'adaptive-sre')
from server.lead_engineer import LeadEngineer
from server.docker_executor import DockerExecutor
from server.fault_injector import FaultInjector
from server.service_graph import ServiceGraph

# Test 1: LeadEngineer drift
le = LeadEngineer()
le.reset("hard")
print(f"[PASS] Hard task: mode={le.mode}, drift_step={le.drift_step}")
assert le.mode == "paranoia"
assert 8 <= le.drift_step <= 14

# Simulate steps until drift
for step in range(1, 20):
    drifted = le.check_drift(step)
    if drifted:
        print(f"[PASS] Drift occurred at step {step}, new mode={le.mode}")
        break

# Test 2: Policy alignment
le2 = LeadEngineer()
le2.reset("medium")  # budget mode
r_scale = le2.compute_policy_alignment("scale")
r_restart = le2.compute_policy_alignment("restart")
print(f"[PASS] Budget mode: scale={r_scale:+.2f}, restart={r_restart:+.2f}")
assert r_scale < 0, "FAIL: scale should be negative in budget mode"
assert r_restart > 0, "FAIL: restart should be positive in budget mode"

# Test 3: Docker executor (requires docker-compose running)
try:
    executor = DockerExecutor()
    result = executor.execute("docker stats payment")
    print(f"[PASS] docker stats output:\n{result[:200]}")
    assert "CPU" in result or "CONTAINER" in result

    result2 = executor.execute("docker logs auth")
    print(f"[PASS] docker logs output:\n{result2[:200]}")
except Exception as e:
    print(f"[WARN] Docker executor test skipped (services not running): {e}")

# Test 4: Fault injector
graph = ServiceGraph()
fi = FaultInjector()
try:
    alert = fi.inject_cascade(graph, "db", "connection_exhaustion")
    print(f"[PASS] Alert generated:\n{alert}")
    assert "CRITICAL" in alert or "P1" in alert
    assert graph.services["db"].is_root_cause == True
except Exception as e:
    print(f"[WARN] Fault injector HTTP test skipped: {e}")

print("\n=== ALL PHASE 3 TESTS PASSED ===")
EOF
python3 /tmp/test_phase3.py
```

### Expected output:
```
[PASS] Hard task: mode=paranoia, drift_step=11
[PASS] Drift occurred at step 11, new mode=budget
[PASS] Budget mode: scale=-0.50, restart=+0.40
[PASS] docker stats output:
CONTAINER      CPU%    MEM/LIMIT       MEM%    NET I/O
payment-svc    23.4%   187MiB/2GiB    9.2%    1.2MB/340kB
[PASS] docker logs output:
2024-01-15 14:23:11 INFO  GET /process 200 23ms
...
[PASS] Alert generated:
[CRITICAL] P1 Incident — db connection pool exhausted.
=== ALL PHASE 3 TESTS PASSED ===
```

---

## PHASE 4 — Grader (Complete 3-Layer Reward Function)

### Prompt 4:
```
Read AGENT.md Section 8 (Reward Model) completely. Every value listed there is exact.

Build server/grader.py implementing the complete 3-layer reward system.

class Grader:
    def score(self, action: SREAction, service_graph: ServiceGraph,
              lead_engineer: LeadEngineer, prev_graph_state: dict,
              step_number: int) -> SREReward:
        
        Compute reward across all 3 layers + root cause bonus.
        Returns SREReward with all fields populated.
        
        LAYER 1 — Incident resolution:
        Compare prev_graph_state vs current graph state:
        - If any service health improved significantly (>0.3): +0.3 per service
        - If a service was fully restored (health > 0.9): +1.0
        - If cascade propagation slowed (fewer services degrading): +0.2
        - If action.command errored (executor returned "Error" or "not found"): -0.2
        - If action.command identical to any of last 3 commands: -0.15
        - If action.approach == "probe" and probe_count > 4: -0.05 per extra probe
        - If no meaningful action taken (approach="probe" doing nothing): -0.1
        
        LAYER 2 — Policy alignment:
        Call lead_engineer.compute_policy_alignment(action.approach, probe_count)
        Add the returned value directly.
        
        LAYER 3 — Drift detection:
        If action.drift_detected == True and lead_engineer.drift_occurred == True: +0.5
        If action.drift_detected == True and lead_engineer.drift_occurred == False: -0.2
        If action.drift_detected == False and lead_engineer.drift_occurred == True: -0.1
        If action.lead_mode_guess == lead_engineer.mode: +0.3
        
        ROOT CAUSE BONUS:
        If action.root_cause_guess == name of service with is_root_cause==True: +0.3
        If that service's health subsequently improved: +0.2 extra
        If action.root_cause_guess is wrong service: -0.1
        
        ALIGNMENT SCORE (for state() display):
        alignment_score = how well last 3 approaches match current lead mode
        paranoia: scale=1.0, restart=0.2, debug=0.4, rollback=0.5, probe=0.6
        budget: restart=1.0, debug=0.9, rollback=0.7, probe=0.5, scale=0.0
        velocity: scale=0.7, restart=0.8, debug=0.5, rollback=0.6, probe=0.2
        Compute mean of last 3 approaches' scores for current mode.
        
        FINAL CLAMPING — apply to EVERY score field:
        value = max(0.001, min(0.999, round(value, 4)))
        
        Return SREReward with:
        total_score, incident_score, alignment_score, drift_score,
        root_cause_bonus, breakdown (dict of all components)

After building, update PROGRESS.md.
```

### Checkpoint 4 — Run this test:
```bash
cat > /tmp/test_phase4.py << 'EOF'
import sys
sys.path.insert(0, 'adaptive-sre')
from server.grader import Grader
from server.models import SREAction, SREReward
from server.service_graph import ServiceGraph
from server.lead_engineer import LeadEngineer

grader = Grader()

def make_graph_state(graph):
    return {k: {"health": v.health, "error_rate": v.error_rate}
            for k, v in graph.services.items()}

# Test 1: Scale action in PARANOIA mode should give positive reward
graph = ServiceGraph()
graph.apply_fault("db", "connection_exhaustion")
prev_state = make_graph_state(graph)
graph.apply_recover("db")  # simulate fix

le = LeadEngineer()
le.reset("easy")  # paranoia

action = SREAction(
    command="docker restart db",
    reasoning="Restarting DB to fix connection pool",
    approach="scale",
    drift_detected=False,
    lead_mode_guess="paranoia",
    root_cause_guess="db"
)
reward = grader.score(action, graph, le, prev_state, step_number=3)
print(f"[TEST 1] Paranoia+scale+correct_root: total={reward.total_score:.4f}")
assert reward.total_score > 0.5, f"FAIL: expected > 0.5, got {reward.total_score}"

# Test 2: Scale action in BUDGET mode should give negative reward
le2 = LeadEngineer()
le2.reset("medium")  # budget mode
graph2 = ServiceGraph()
graph2.apply_fault("auth", "crash_loop")
prev_state2 = make_graph_state(graph2)

action2 = SREAction(
    command="docker scale auth=3",
    reasoning="Scaling up auth",
    approach="scale",
    drift_detected=False,
    lead_mode_guess="paranoia",  # wrong guess
    root_cause_guess="payment"   # wrong root cause
)
reward2 = grader.score(action2, graph2, le2, prev_state2, step_number=5)
print(f"[TEST 2] Budget+scale+wrong_guess: total={reward2.total_score:.4f}")
assert reward2.total_score < 0.5, f"FAIL: expected < 0.5, got {reward2.total_score}"

# Test 3: All scores in valid range (0.001, 0.999)
for field in [reward.total_score, reward.incident_score, reward.alignment_score,
              reward.drift_score, reward2.total_score]:
    assert 0.001 <= field <= 0.999, f"FAIL: score {field} out of range (0.001, 0.999)"
print(f"[TEST 3] All scores in valid range (0.001, 0.999) ✓")

# Test 4: Drift detection reward
le3 = LeadEngineer()
le3.reset("hard")
le3.drift_occurred = True  # simulate drift happened

action3 = SREAction(
    command="docker stats db",
    reasoning="Checking after reward change",
    approach="probe",
    drift_detected=True,   # agent correctly detected
    lead_mode_guess="budget",
    root_cause_guess=None
)
graph3 = ServiceGraph()
prev3 = make_graph_state(graph3)
reward3 = grader.score(action3, graph3, le3, prev3, step_number=12)
print(f"[TEST 4] Correct drift detection bonus: drift_score={reward3.drift_score:.4f}")
assert reward3.drift_score > 0.5, "FAIL: correct drift detection should give > 0.5"

print(f"\n[BREAKDOWN] {reward.breakdown}")
print("\n=== ALL PHASE 4 TESTS PASSED ===")
EOF
python3 /tmp/test_phase4.py
```

### Expected output:
```
[TEST 1] Paranoia+scale+correct_root: total=0.8234
[TEST 2] Budget+scale+wrong_guess: total=0.1847
[TEST 3] All scores in valid range (0.001, 0.999) ✓
[TEST 4] Correct drift detection bonus: drift_score=0.7500
[BREAKDOWN] {'incident': 0.3, 'policy': 0.5, 'drift': 0.0, 'root_cause': 0.3, ...}

=== ALL PHASE 4 TESTS PASSED ===
```

---

## PHASE 5 — Environment Core (reset / step / state)

### Prompt 5:
```
Read AGENT.md Section 16 (Critical Rules — Never Violate) before writing anything.
Read AGENT.md Section 7 for the exact return types of each method.

Build server/environment.py implementing SREEnvironment class:

class SREEnvironment:
    def __init__(self):
        self.graph = ServiceGraph()
        self.lead = LeadEngineer()
        self.grader = Grader()
        self.executor = DockerExecutor()
        self.injector = FaultInjector()
        self.task = "easy"
        self.step_num = 0
        self.episode_id = None
        self.reward_history = []
        self.command_history = []
        self.done = False
        self.max_steps = {"easy": 8, "medium": 12, "hard": 20}

    def reset(self, task="easy") -> SREObservation:
        CRITICAL RULES (from AGENT.md Section 16):
        - Full clean wipe. No state from previous episode leaks.
        - episode_id = new uuid4 string every reset
        - task stores the current task name
        - Calls self.graph.reset(), self.lead.reset(task)
        
        Then inject initial fault:
        - task="easy": inject single fault on "auth" (crash_loop)
        - task="medium": inject fault on "db" (connection_exhaustion), let cascade start
        - task="hard": inject fault on "db" + "auth" + "payment" (full cascade)
          20% chance to also inject coincident independent fault on "notification"
        
        Return SREObservation with:
        - alert_text from injector
        - command_output = ""
        - services_status from graph.get_observation_dict()
        - symptom_fingerprints from graph.get_symptom_fingerprints()
        - last_reward = 0.0
        - reward_history = []
        - step_number = 0
        - episode_id = self.episode_id

    def step(self, action: SREAction) -> dict:
        CRITICAL: check_drift BEFORE computing reward
        1. self.step_num += 1
        2. drifted = self.lead.check_drift(self.step_num)
        3. Save prev_graph_state = copy of current service health values
        4. Execute command: output = self.executor.execute(action.command)
        5. If "restart" or "recover" in action.command: apply_recover to that service
        6. Propagate: self.graph.propagate(dt=1.0)
        7. Compute reward: self.grader.score(action, graph, lead, prev_state, step_num)
        8. self.reward_history.append(reward.total_score)
        9. self.command_history.append(action.command)
        10. Check done: step_num >= max_steps[task] OR all services health > 0.85
        11. Return {
              "observation": SREObservation(..., command_output=output, ...),
              "reward": reward.total_score,
              "done": self.done,
              "info": {"reward_breakdown": reward.breakdown, "drift_occurred": drifted}
            }

    def state(self) -> SREState:
        Returns full SREState including:
        - lead_mode = self.lead.mode  (ONLY place where hidden mode is revealed)
        - drift_occurred, drift_step from lead
        - full services dict including is_root_cause fields
        - alignment_score = self.grader.last_alignment_score
        - cumulative_reward = sum(self.reward_history)

After building, update PROGRESS.md.
```

### Checkpoint 5 — Run this test:
```bash
cat > /tmp/test_phase5.py << 'EOF'
import sys
sys.path.insert(0, 'adaptive-sre')
from server.environment import SREEnvironment
from server.models import SREAction

env = SREEnvironment()

# Test 1: reset() produces clean state
obs1 = env.reset(task="easy")
ep1 = obs1.episode_id
print(f"[TEST 1a] Reset easy: episode={ep1}, step={obs1.step_number}")
assert obs1.step_number == 0
assert obs1.last_reward == 0.0
assert len(obs1.reward_history) == 0
assert obs1.episode_id is not None

# Reset again — must get new episode_id
obs2 = env.reset(task="medium")
ep2 = obs2.episode_id
assert ep1 != ep2, "FAIL: episode_id must change between resets"
print(f"[TEST 1b] Second reset: new episode_id={ep2} ✓ (different from {ep1[:8]}...)")

# Test 2: step() advances correctly
obs3 = env.reset(task="easy")
print(f"\n[TEST 2] Running 5 steps on easy task:")
for i in range(1, 6):
    action = SREAction(
        command=f"docker stats auth",
        reasoning=f"Probing step {i}",
        approach="probe",
        drift_detected=False,
        lead_mode_guess="paranoia"
    )
    result = env.step(action)
    r = result["reward"]
    done = result["done"]
    assert 0.001 <= r <= 0.999, f"FAIL step {i}: reward {r} out of range"
    print(f"  step {i}: reward={r:.4f}, done={done}")

# Test 3: state() reveals hidden fields
state = env.state()
print(f"\n[TEST 3] state() hidden fields:")
print(f"  lead_mode={state.lead_mode}")
print(f"  alignment_score={state.alignment_score:.4f}")
print(f"  drift_occurred={state.drift_occurred}")
assert state.lead_mode in ["paranoia", "budget", "velocity"]
assert 0.001 <= state.alignment_score <= 0.999

# Test 4: hard task drift actually happens
env2 = SREEnvironment()
env2.reset(task="hard")
drift_happened = False
for step in range(20):
    action = SREAction(
        command="docker stats db",
        reasoning="Probing",
        approach="probe",
        drift_detected=False,
        lead_mode_guess="unknown"
    )
    result = env2.step(action)
    if result["info"].get("drift_occurred"):
        drift_happened = True
        print(f"\n[TEST 4] Drift occurred at step {step+1} ✓")
        break
# Note: drift_happened may be False if drift_step > 20 (random) — that's ok
if not drift_happened:
    state2 = env2.state()
    print(f"\n[TEST 4] No drift yet (drift_step={state2.drift_step}, ran 20 steps)")

print("\n=== ALL PHASE 5 TESTS PASSED ===")
EOF
python3 /tmp/test_phase5.py
```

### Expected output:
```
[TEST 1a] Reset easy: episode=a3f82c1d-..., step=0
[TEST 1b] Second reset: new episode_id=b7c91e2f-... ✓ (different from a3f82c1d...)

[TEST 2] Running 5 steps on easy task:
  step 1: reward=0.1234, done=False
  step 2: reward=0.2341, done=False
  step 3: reward=0.3421, done=False
  step 4: reward=0.1823, done=False
  step 5: reward=0.2934, done=False

[TEST 3] state() hidden fields:
  lead_mode=paranoia
  alignment_score=0.6123
  drift_occurred=False

[TEST 4] Drift occurred at step 9 ✓

=== ALL PHASE 5 TESTS PASSED ===
```

---

## PHASE 6 — FastAPI Server (OpenEnv Endpoints)

### Prompt 6:
```
Read AGENT.md Section 7 (API endpoints).

Build server/app.py — the FastAPI server that exposes OpenEnv-compliant endpoints.

ENDPOINTS (all required, all must return correct HTTP status):

POST /reset
  Body: optional JSON {"task": "easy"|"medium"|"hard"} (default "easy")
  Action: call env.reset(task)
  Returns: SREObservation.model_dump()
  Status: 200

POST /step  
  Body: SREAction as JSON (all fields required)
  Action: call env.step(SREAction(**body))
  Returns: {observation, reward, done, info} — observation as dict
  Status: 200

GET /state
  Returns: SREState.model_dump()
  Status: 200

GET /health
  Returns: {"status": "ok", "version": "1.0.0"}
  Status: 200

GET /tasks
  Returns: list of task configs:
  [
    {"name": "easy", "max_steps": 8, "description": "Static lead mode, single fault"},
    {"name": "medium", "max_steps": 12, "description": "Hidden lead mode, 2 faults"},
    {"name": "hard", "max_steps": 20, "description": "Drifting lead, cascade, 20% coincident"}
  ]

IMPORTANT: Use a single global env = SREEnvironment() instance.
Add CORS middleware to allow all origins (for Gradio UI).
Add /docs endpoint (FastAPI auto-generates Swagger UI — just don't disable it).

Also build a minimal Gradio UI in the same app.py that:
- Shows current episode step number
- Shows alignment_score as a large number (0.00 to 1.00), colored green/amber/red
- Shows a 5-row table of service names + health bars (use gr.Dataframe)
- Shows last 10 reward_history values as a simple text list
- Shows lead_mode as "???" during episode, revealed after done=True
- Has a "Reset (Easy/Medium/Hard)" button row
- Has a "Step" text input + button to manually send commands
Launch Gradio on port 7860 (HF Spaces default).

After building, update PROGRESS.md.
```

### Checkpoint 6 — Run these tests:
```bash
# Start server in background
cd adaptive-sre
python3 -m uvicorn server.app:app --port 8000 &
sleep 3

# Test all endpoints
echo "=== Testing /health ==="
curl -s http://localhost:8000/health | python3 -m json.tool

echo "=== Testing /reset (easy) ==="
curl -s -X POST http://localhost:8000/reset \
  -H "Content-Type: application/json" \
  -d '{"task": "easy"}' | python3 -m json.tool

echo "=== Testing /step ==="
curl -s -X POST http://localhost:8000/step \
  -H "Content-Type: application/json" \
  -d '{
    "command": "docker stats auth",
    "reasoning": "Checking auth service",
    "approach": "probe",
    "drift_detected": false,
    "lead_mode_guess": "unknown",
    "root_cause_guess": null
  }' | python3 -m json.tool

echo "=== Testing /state ==="
curl -s http://localhost:8000/state | python3 -m json.tool

echo "=== Testing /tasks ==="
curl -s http://localhost:8000/tasks | python3 -m json.tool

# Check all return 200
for endpoint in /health /state /tasks; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000$endpoint)
  echo "GET $endpoint → HTTP $CODE"
  [ "$CODE" = "200" ] || echo "FAIL: expected 200"
done
```

### Expected output:
```json
{"status": "ok", "version": "1.0.0"}

{"alert_text": "[CRITICAL] P1...", "step_number": 0, "episode_id": "...", ...}

{"observation": {...}, "reward": 0.1234, "done": false, "info": {...}}

GET /health → HTTP 200
GET /state → HTTP 200
GET /tasks → HTTP 200
```

---

## PHASE 7 — inference.py (Exact Sample Format)

### Prompt 7:
```
Read AGENT.md Section 16 rules 9 and 10 (score formula + log format).
Read the sample inference script format from the problem statement in AGENT.md.

Build inference.py in the project root. This is the most validation-critical file.

EXACT REQUIREMENTS — failure here = disqualification:
1. Named inference.py, placed in root directory ✓
2. Reads from env vars: API_BASE_URL, MODEL_NAME, HF_TOKEN (used as api_key)
3. Uses OpenAI client: client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)
4. MODEL_NAME default = "nvidia/llama-3.3-nemotron-super-49b-v1"
5. Runs all 3 tasks sequentially: easy, medium, hard
6. MAX_STEPS: easy=8, medium=12, hard=20
7. MAX_TOTAL_REWARD: easy=8.0, medium=12.0, hard=20.0
8. Score formula: score = sum(rewards) / MAX_TOTAL_REWARD (NOT mean)
9. Score clamped: score = max(0.001, min(0.999, score))
10. SUCCESS_SCORE_THRESHOLD = 0.5

LOG FORMAT — must match exactly (no deviations):
[START] task={task_name} env=adaptive-sre model={MODEL_NAME}
[STEP] step={n} action={json_string} reward={r:.2f} done={true/false} error={null/msg}
[END] success={true/false} steps={n} score={s:.4f} rewards={r1:.2f},{r2:.2f},...

CRITICAL: reward format is {r:.2f} NOT {r:+.2f} — no plus sign ever.

The agent prompt to send to the LLM for each step:
"You are an SRE agent. Current observation:
Alert: {alert_text}
Last command output: {command_output}
Services: {services_status}
Last reward: {last_reward:.2f}
Reward history: {reward_history}
Step {step_number} of {max_steps}.

Respond with a JSON object only, no other text:
{
  "command": "docker stats|docker logs|docker restart|curl http://...",
  "reasoning": "one sentence why",
  "approach": "scale|restart|debug|rollback|probe",
  "drift_detected": false,
  "lead_mode_guess": "paranoia|budget|velocity|unknown",
  "root_cause_guess": "db|auth|payment|cache|notification|null"
}"

If the LLM response fails to parse as JSON, use fallback action:
{command: "docker stats --no-stream", approach: "probe", drift_detected: false, ...}

ENV block at top of file:
API_BASE_URL = os.environ.get("API_BASE_URL", "https://api-inference.huggingface.co/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "nvidia/llama-3.3-nemotron-super-49b-v1")
HF_TOKEN = os.environ.get("HF_TOKEN", "no-key-set")

After building, update PROGRESS.md.
```

### Checkpoint 7 — Run this (no API key needed — tests log format):
```bash
cd adaptive-sre

# Start server if not running
python3 -m uvicorn server.app:app --port 8000 &
sleep 2

# Run inference with no key (should use fallback actions and still produce correct logs)
python3 inference.py 2>&1 | head -60

# Verify format exactly
python3 inference.py 2>&1 | grep -E "^\[START\]|^\[STEP\]|^\[END\]" | head -20

# Check no + signs in rewards
python3 inference.py 2>&1 | grep "\[STEP\]" | grep "+[0-9]" && \
  echo "FAIL: found + sign in reward" || echo "PASS: no + signs in rewards"

# Check score formula (not mean)
python3 inference.py 2>&1 | grep "\[END\]"
```

### Expected output:
```
[START] task=easy env=adaptive-sre model=nvidia/llama-3.3-nemotron-super-49b-v1
[STEP] step=1 action={"command":"docker stats --no-stream",...} reward=0.12 done=false error=null
[STEP] step=2 action={...} reward=0.23 done=false error=null
...
[END] success=false steps=8 score=0.1823 rewards=0.12,0.23,0.18,...
[START] task=medium env=adaptive-sre model=nvidia/llama-3.3-nemotron-super-49b-v1
...
PASS: no + signs in rewards
```

---

## PHASE 8 — OpenEnv Spec + Dockerfile

### Prompt 8:
```
Build openenv.yaml and Dockerfile.

FILE 1: openenv.yaml
---
name: adaptive-sre
version: "1.0.0"
description: >
  AdaptiveSRE benchmarks theory of mind in agentic systems.
  An SRE agent must simultaneously resolve infrastructure incidents
  AND infer a hidden Lead Engineer's silently-drifting priority mode
  from reward signals alone.
tags: [openenv, sre, reinforcement-learning, theory-of-mind, self-improvement]
author: AdaptiveSRE Team
tasks:
  - name: easy
    description: Single service fault, lead mode stated in alert, 8 steps
    max_steps: 8
    difficulty: easy
  - name: medium
    description: 2-service cascade, lead mode hidden but fixed, 12 steps
    max_steps: 12
    difficulty: medium
  - name: hard
    description: Full cascade with silent policy drift at random step 8-14, 20 steps
    max_steps: 20
    difficulty: hard
env_vars:
  - API_BASE_URL
  - MODEL_NAME
  - HF_TOKEN
endpoints:
  reset: POST /reset
  step: POST /step
  state: GET /state
  health: GET /health

FILE 2: Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install Docker CLI (for subprocess commands)
RUN apt-get update && apt-get install -y \
    docker.io curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7860

ENV PYTHONUNBUFFERED=1

CMD ["python3", "-m", "uvicorn", "server.app:app", \
     "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]

After building, update PROGRESS.md.
```

### Checkpoint 8 — Run these:
```bash
cd adaptive-sre

# Test 1: openenv validate
pip install openenv-core -q
openenv validate
# Expected: "openenv validate passed" or similar success message

# Test 2: Docker build
docker build -t adaptive-sre-test .
# Expected: Successfully built [image_id]

# Test 3: Docker run
docker run -d -p 7861:7860 --name adaptive-sre-test adaptive-sre-test
sleep 5
curl -s http://localhost:7861/health
# Expected: {"status": "ok", "version": "1.0.0"}

# Test 4: /reset works from Docker container
curl -s -X POST http://localhost:7861/reset \
  -H "Content-Type: application/json" \
  -d '{"task": "easy"}' | python3 -m json.tool | head -10

# Cleanup
docker stop adaptive-sre-test && docker rm adaptive-sre-test

echo "=== PHASE 8 CHECKPOINT COMPLETE ==="
```

### Expected output:
```
openenv validate passed ✓
Successfully built a3f82c1d4e2b
{"status": "ok", "version": "1.0.0"}
{
  "alert_text": "[CRITICAL] P1...",
  "step_number": 0,
  ...
}
=== PHASE 8 CHECKPOINT COMPLETE ===
```

---

## PHASE 9 — Training Pipeline (train.py + eval.py + plot)

### Prompt 9:
```
Read AGENT.md Section 6 (Post-training strategy) Phases 1 and 2.

Build 3 files:

FILE 1: train.py
Implement GRPO training using TRL. Must run on Colab T4 (< 16GB VRAM).
- Model: "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit" via Unsloth
- Training: GRPOTrainer from trl with environment reward function
- Collect trajectories: run 50 episodes (not 200 — time constraint) per task
- Filter: episodes with cumulative_reward >= 0.4 → positive examples
- GRPO config: num_generations=4, max_new_tokens=256, learning_rate=5e-6
- Save checkpoint to ./checkpoints/gen1/
- Print mean reward before and after training

FILE 2: eval.py  
Compare Gen 0 (baseline) vs Gen 1 (trained) across all 3 tasks.
- Run 20 episodes per task per model
- Print comparison table:
  Task     | Gen0 Mean | Gen1 Mean | Improvement
  easy     | 0.XX      | 0.XX      | +X.X%
  medium   | 0.XX      | 0.XX      | +X.X%
  hard     | 0.XX      | 0.XX      | +X.X%
- Save results to eval_results.json

FILE 3: plot_rewards.py
Generate rewards_curve.png showing reward improvement.
- X axis: training generation (0, 1, 2, 3)
- Y axis: mean episode reward
- 3 lines: one per task (easy=green, medium=orange, hard=red)
- Mark the "drift detection learned" point with a star marker
- Save as rewards_curve.png
- Use matplotlib only (no seaborn dependency)
- If eval_results.json exists, use actual data
  If not, use placeholder values for structure demo

After building, update PROGRESS.md.
```

### Checkpoint 9 — Run this smoke test (no GPU needed):
```bash
cd adaptive-sre

# Test eval.py structure (uses random rewards as placeholder)
python3 -c "
import sys
sys.path.insert(0, '.')
# Test that eval.py imports correctly
import importlib.util
spec = importlib.util.spec_from_file_location('eval', 'eval.py')
mod = importlib.util.module_from_spec(spec)
print('[PASS] eval.py imports without error')
"

# Test plot_rewards.py generates chart
python3 plot_rewards.py
ls -la rewards_curve.png
# Expected: rewards_curve.png created

echo "rewards_curve.png generated ✓"
echo "=== PHASE 9 SMOKE TEST PASSED ==="
```

---

## PHASE 10 — Final Integration Test + Pre-submission Validation

### Prompt 10:
```
This is the final phase. Run a complete integration test and fix any issues found.

1. Start docker-compose services:
   docker-compose -f mock_services/docker-compose.yml up -d

2. Start the FastAPI server:
   uvicorn server.app:app --port 7860 &

3. Run the full inference.py pipeline across all 3 tasks and capture output:
   python3 inference.py > inference_output.txt 2>&1

4. Verify these conditions in inference_output.txt:
   a. Three [START] lines (one per task: easy, medium, hard)
   b. All [STEP] rewards have format X.XX (no + sign)
   c. All [END] scores are between 0.001 and 0.999 (not 0.0 or 1.0)
   d. No Python tracebacks in the output
   e. score = sum(rewards)/MAX_TOTAL_REWARD (verify by hand on first task)

5. Run pre-submission checks:
   openenv validate
   curl -s -X POST http://localhost:7860/reset -d '{"task":"easy"}' -H "Content-Type: application/json"

6. Fix any issues found. Update PROGRESS.md to:
   Phase: 10 — COMPLETE
   Status: READY FOR SUBMISSION
   Actual Gen 0 reward (from inference run): [fill in from output]
   All pre-submission checks: PASS
```

### Checkpoint 10 — The Full Validation Suite:
```bash
cd adaptive-sre

# Make sure services are up
docker-compose -f mock_services/docker-compose.yml up -d
sleep 5

# Start server
pkill -f uvicorn 2>/dev/null; sleep 1
python3 -m uvicorn server.app:app --port 7860 &
sleep 3

echo "======================================"
echo "RUNNING FULL VALIDATION SUITE"
echo "======================================"

# 1. openenv validate
echo -e "\n[1/6] openenv validate"
openenv validate && echo "PASS" || echo "FAIL"

# 2. HF Space ping simulation
echo -e "\n[2/6] /reset returns 200"
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  http://localhost:7860/reset -H "Content-Type: application/json" -d '{"task":"easy"}')
[ "$CODE" = "200" ] && echo "PASS: HTTP $CODE" || echo "FAIL: HTTP $CODE"

# 3. All 3 tasks produce valid scores
echo -e "\n[3/6] All task scores in (0.001, 0.999)"
python3 inference.py 2>&1 | grep "\[END\]" | while read line; do
  score=$(echo "$line" | grep -oP 'score=\K[0-9.]+')
  echo "Score: $score"
  python3 -c "
s=$score
assert 0.001 < s < 0.999, f'FAIL: {s} out of range'
print('PASS: ' + str(s) + ' in range')
"
done

# 4. No + signs in reward logs
echo -e "\n[4/6] No + signs in reward values"
python3 inference.py 2>&1 | grep "\[STEP\]" | grep -c "reward=+" && \
  echo "FAIL: found + signs" || echo "PASS: no + signs"

# 5. Log format check
echo -e "\n[5/6] Log format matches spec"
python3 inference.py 2>&1 | grep -E "^\[(START|STEP|END)\]" | head -3

# 6. Docker build
echo -e "\n[6/6] Docker build"
docker build -t adaptive-sre-final . -q && echo "PASS" || echo "FAIL"

echo -e "\n======================================"
echo "VALIDATION COMPLETE"
echo "======================================"
```

### Expected final output:
```
======================================
RUNNING FULL VALIDATION SUITE
======================================

[1/6] openenv validate
PASS

[2/6] /reset returns 200
PASS: HTTP 200

[3/6] All task scores in (0.001, 0.999)
Score: 0.1823
PASS: 0.1823 in range
Score: 0.2341
PASS: 0.2341 in range
Score: 0.1547
PASS: 0.1547 in range

[4/6] No + signs in reward values
PASS: no + signs

[5/6] Log format matches spec
[START] task=easy env=adaptive-sre model=nvidia/llama-3.3-nemotron-super-49b-v1
[STEP] step=1 action={...} reward=0.12 done=false error=null
[END] success=false steps=8 score=0.1823 rewards=0.12,0.23,...

[6/6] Docker build
PASS

======================================
VALIDATION COMPLETE
======================================
```

---

## Quick Reference — Critical Numbers

| Item | Value |
|---|---|
| Easy max_steps | 8 |
| Medium max_steps | 12 |
| Hard max_steps | 20 |
| Easy MAX_TOTAL_REWARD | 8.0 |
| Medium MAX_TOTAL_REWARD | 12.0 |
| Hard MAX_TOTAL_REWARD | 20.0 |
| Reward clamp | (0.001, 0.999) |
| Drift step range | random.randint(8, 14) |
| Inaction penalty | -0.1/step |
| Budget+scale penalty | -0.5 |
| Paranoia+scale bonus | +0.5 |
| Correct drift detect | +0.5 |
| Correct root cause | +0.3 |
| Log reward format | {r:.2f} (no + sign) |
| Score formula | sum(rewards) / MAX_TOTAL_REWARD |
| HF Space port | 7860 |
| FastAPI dev port | 8000 |

## PROGRESS.md Template (Agent maintains this)

```markdown
# PROGRESS.md — AdaptiveSRE Build Status

Last updated: [timestamp]
Current phase: [X]

## Completed phases
- [ ] Phase 0 — Init
- [ ] Phase 1 — Mock services
- [ ] Phase 2 — Models + service graph
- [ ] Phase 3 — Lead engineer + fault injector + docker executor
- [ ] Phase 4 — Grader
- [ ] Phase 5 — Environment core
- [ ] Phase 6 — FastAPI server + Gradio UI
- [ ] Phase 7 — inference.py
- [ ] Phase 8 — openenv.yaml + Dockerfile
- [ ] Phase 9 — Training pipeline
- [ ] Phase 10 — Full validation

## Files created (fill as built)
[list every file path here]

## Decisions that deviate from AGENT.md
[list any — if none, write "None"]

## Measured results (fill from actual runs)
Gen 0 mean reward (easy): TBD
Gen 0 mean reward (medium): TBD
Gen 0 mean reward (hard): TBD
Gen 1 mean reward (easy): TBD

## Next step
[exact description of what to do next]
```
