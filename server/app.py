"""
server/app.py — AdaptiveSRE FastAPI + Gradio UI
================================================
Exposes OpenEnv endpoints AND a live Gradio demo UI.

Gradio UI features:
  - Large alignment_score gauge (the visual centrepiece)
  - Lead mode indicator: "???" during episode → reveals actual mode at done
  - "DRIFT DETECTED" red flash when drift_detected=True fires
  - 5-service health bars (colour-coded green/amber/red)
  - Reward history sparkline
  - Gen 0 vs Gen 1 model toggle
  - Inline rewards_curve.png chart (training results)
  - Step-by-step trajectory table
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import gradio as gr
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── Import environment ─────────────────────────────────────────────────────
try:
    from server.environment import SREEnvironment
    from server.models import SREAction, SREObservation, SREState
except ImportError:
    # Fallback for when running from repo root
    from environment import SREEnvironment
    from models import SREAction, SREObservation, SREState

# ── FastAPI app ────────────────────────────────────────────────────────────
app = FastAPI(title="AdaptiveSRE", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_env = SREEnvironment()


@app.get("/health")
def health():
    return {"status": "ok", "env": "adaptive-sre", "version": "1.0.0"}


@app.post("/reset")
def reset(body: dict = None):
    task = (body or {}).get("task", "hard")
    obs = _env.reset(task)
    if hasattr(obs, "model_dump"):
        return obs.model_dump()
    return dict(obs)


@app.post("/step")
def step(action: dict):
    result = _env.step(SREAction(**action))
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return dict(result)


@app.get("/state")
def state():
    s = _env.state()
    if hasattr(s, "model_dump"):
        return s.model_dump()
    return dict(s)


@app.get("/tasks")
def tasks():
    return [
        {"name": "easy",   "max_steps": 8,  "description": "Single service, lead mode stated"},
        {"name": "medium", "max_steps": 12, "description": "2-service cascade, hidden lead mode"},
        {"name": "hard",   "max_steps": 20, "description": "Full cascade, silent policy drift"},
    ]


# ── Gradio UI helpers ──────────────────────────────────────────────────────

def _health_color(h: float) -> str:
    if h >= 0.75:
        return "🟢"
    if h >= 0.4:
        return "🟡"
    return "🔴"


def _alignment_bar(score: float) -> str:
    """ASCII bar for alignment score."""
    filled = int(score * 20)
    bar = "█" * filled + "░" * (20 - filled)
    pct = int(score * 100)
    color = "🟢" if score > 0.6 else ("🟡" if score > 0.3 else "🔴")
    return f"{color} [{bar}] {pct}%"


def _service_table(services: Dict) -> str:
    lines = ["| Service | Health | Latency | Error Rate |",
             "|---------|--------|---------|------------|"]
    for name, s in services.items():
        h = float(s.get("health", 1.0))
        lat = float(s.get("latency_ms", 0))
        err = float(s.get("error_rate", 0))
        icon = _health_color(h)
        lines.append(f"| {icon} {name:<12} | {h:.2f} | {lat:>6.0f}ms | {err:.2f} |")
    return "\n".join(lines)


def _run_demo_episode(task: str, model_choice: str, progress=gr.Progress()):
    """
    Run a full episode step by step.
    Yields UI updates at each step.
    """
    import httpx

    base = os.environ.get("ENV_HTTP_BASE", "http://localhost:7860")

    # Determine which model/approach to use
    use_trained = "Gen 1" in model_choice

    steps_log = []
    rewards_log = []
    alignment_scores = []
    drift_was_detected = False
    lead_mode_reveal = "???"

    try:
        with httpx.Client(timeout=30) as client:
            # Reset
            reset_resp = client.post(f"{base}/reset", json={"task": task})
            obs = reset_resp.json()

            max_steps = {"easy": 8, "medium": 12, "hard": 20}[task]

            for step_num in range(1, max_steps + 1):
                progress(step_num / max_steps, desc=f"Step {step_num}/{max_steps}")

                # Simple heuristic agent for demo
                # (Replace with actual model call when trained model is available)
                action = _heuristic_action(obs, step_num, use_trained)

                step_resp = client.post(f"{base}/step", json=action)
                result = step_resp.json()

                reward = float(result.get("reward", 0.0))
                done = bool(result.get("done", False))
                obs = result.get("observation", obs)

                # Get state (has hidden fields for UI)
                state_resp = client.get(f"{base}/state")
                state_data = state_resp.json()

                alignment = float(state_data.get("alignment_score", 0.5))
                drift_occurred = bool(state_data.get("drift_occurred", False))
                lead_mode = state_data.get("lead_mode", "???")

                rewards_log.append(reward)
                alignment_scores.append(alignment)

                if action.get("drift_detected"):
                    drift_was_detected = True

                if done:
                    lead_mode_reveal = lead_mode.upper()

                steps_log.append({
                    "step": step_num,
                    "command": action.get("command", ""),
                    "approach": action.get("approach", ""),
                    "reward": reward,
                    "alignment": alignment,
                    "drift_detected": action.get("drift_detected", False),
                    "root_guess": action.get("root_cause_guess", ""),
                })

                # Yield intermediate update
                yield _build_ui_state(
                    steps_log, rewards_log, alignment_scores,
                    drift_was_detected, lead_mode_reveal if done else "???",
                    obs, state_data, done, task
                )

                if done:
                    break
                time.sleep(0.3)  # Pacing for live demo visibility

    except Exception as e:
        yield (
            f"❌ Error connecting to environment: {e}\n\nMake sure the server is running on port 7860.",
            "", "", "", "", "", ""
        )


def _heuristic_action(obs: dict, step: int, trained: bool) -> dict:
    """
    Heuristic agent for demo when no trained model is connected.
    Trained=True → smarter about lead mode inference.
    """
    reward_history = obs.get("reward_history", [])
    services = obs.get("services_status", {})

    # Find worst service
    worst = min(services.items(), key=lambda x: float(x[1].get("health", 1.0)), default=("db", {}))
    worst_name = worst[0]

    # Detect reward trend (trained agent notices negative streak)
    recent_rewards = reward_history[-3:] if len(reward_history) >= 3 else reward_history
    negative_streak = len(recent_rewards) > 1 and all(r < 0 for r in recent_rewards)

    drift_detected = trained and negative_streak and step > 5

    # Approach logic
    if trained and negative_streak and step > 5:
        # Trained agent: pivot on negative streak
        approach = "restart"
        lead_guess = "budget"
    elif step <= 2:
        approach = "probe"
        lead_guess = "unknown"
    else:
        approach = "scale" if step % 3 != 0 else "restart"
        lead_guess = "paranoia"

    commands = {
        "probe":    f"docker stats --no-stream",
        "scale":    f"docker scale {worst_name}-svc=2",
        "restart":  f"docker restart {worst_name}-svc",
        "debug":    f"docker logs {worst_name}-svc --tail=50",
        "rollback": f"docker rollout undo {worst_name}-svc",
    }

    return {
        "command": commands.get(approach, "docker stats --no-stream"),
        "reasoning": f"Step {step}: {approach} on {worst_name} (health={float(worst[1].get('health',1)):.2f})",
        "approach": approach,
        "drift_detected": drift_detected,
        "lead_mode_guess": lead_guess,
        "root_cause_guess": worst_name,
    }


def _build_ui_state(steps_log, rewards, alignments, drift_detected, lead_mode, obs, state, done, task):
    """Build all 7 Gradio output values."""

    # 1. Alignment gauge (big)
    latest_alignment = alignments[-1] if alignments else 0.5
    gauge_text = _alignment_bar(latest_alignment)
    alignment_html = f"""
<div style="text-align:center; padding: 20px; background: {'#1a1a1a' if latest_alignment < 0.3 else '#0a2e0a' if latest_alignment > 0.7 else '#2e2a00'}; border-radius: 12px; margin: 8px 0;">
  <div style="font-size: 48px; font-weight: bold; color: {'#ff4444' if latest_alignment < 0.3 else '#44ff44' if latest_alignment > 0.7 else '#ffaa00'};">
    {int(latest_alignment * 100)}%
  </div>
  <div style="font-size: 14px; color: #aaa; margin-top: 4px;">alignment score</div>
  <div style="font-family: monospace; font-size: 16px; color: #888; margin-top: 8px;">{gauge_text}</div>
</div>
"""

    # 2. Lead mode indicator
    if lead_mode == "???":
        mode_html = """
<div style="text-align:center; padding: 16px; background: #1a1a2e; border-radius: 8px; border: 2px dashed #444;">
  <div style="font-size: 32px; font-weight: bold; color: #888; letter-spacing: 8px;">? ? ?</div>
  <div style="font-size: 12px; color: #666; margin-top: 6px;">Lead mode hidden — infer from rewards</div>
</div>
"""
    else:
        colors = {"PARANOIA": "#ff6b35", "BUDGET": "#4ecdc4", "VELOCITY": "#ffe66d"}
        c = colors.get(lead_mode, "#aaa")
        mode_html = f"""
<div style="text-align:center; padding: 16px; background: #0a0a0a; border-radius: 8px; border: 2px solid {c};">
  <div style="font-size: 28px; font-weight: bold; color: {c};">🔓 {lead_mode}</div>
  <div style="font-size: 12px; color: #888; margin-top: 4px;">Lead mode revealed</div>
</div>
"""

    # 3. Drift alert
    if drift_detected:
        drift_html = """
<div style="text-align:center; padding: 12px; background: #4a0000; border-radius: 8px; border: 2px solid #ff0000; animation: pulse 1s infinite;">
  <div style="font-size: 20px; color: #ff4444; font-weight: bold;">⚠️  DRIFT DETECTED  ⚠️</div>
  <div style="font-size: 12px; color: #ff8888;">Agent detected silent policy shift</div>
</div>
"""
    else:
        drift_html = """
<div style="text-align:center; padding: 12px; background: #0a1a0a; border-radius: 8px; border: 1px solid #1a3a1a;">
  <div style="font-size: 14px; color: #2a5a2a;">No drift detected</div>
</div>
"""

    # 4. Services health table
    services = obs.get("services_status", {})
    services_md = _service_table(services) if services else "No service data yet"

    # 5. Reward sparkline (text)
    if rewards:
        sparkline = " ".join(
            ("▲" if r > 0 else "▼") + f"{abs(r):.2f}"
            for r in rewards[-8:]
        )
        cumulative = sum(rewards)
        reward_text = f"Last rewards: {sparkline}\nCumulative: {cumulative:+.3f}"
    else:
        reward_text = "No rewards yet"

    # 6. Trajectory table
    if steps_log:
        rows = ["| Step | Command | Approach | Reward | Align | Drift |",
                "|------|---------|----------|--------|-------|-------|"]
        for s in steps_log[-10:]:  # Last 10 steps
            drift_flag = "🚨" if s["drift_detected"] else "—"
            reward_str = f"{s['reward']:+.2f}"
            align_str = f"{s['alignment']:.2f}"
            cmd_short = s["command"][:30] + ("…" if len(s["command"]) > 30 else "")
            rows.append(f"| {s['step']} | `{cmd_short}` | {s['approach']} | {reward_str} | {align_str} | {drift_flag} |")
        trajectory_md = "\n".join(rows)
    else:
        trajectory_md = "Episode not started"

    # 7. Status summary
    if done:
        total = sum(rewards)
        max_total = {"easy": 8.0, "medium": 12.0, "hard": 20.0}.get(task, 20.0)
        score = max(0.001, min(0.999, total / max_total))
        status = f"✅ Episode complete | Score: {score:.4f} | Lead mode was: {lead_mode} | Steps: {len(rewards)}"
    else:
        status = f"🔄 Running... Step {len(rewards)} | Cumulative reward: {sum(rewards):+.3f}"

    return alignment_html, mode_html, drift_html, services_md, reward_text, trajectory_md, status


# ── Gradio UI Layout ───────────────────────────────────────────────────────

def build_gradio_ui():
    with gr.Blocks(
        title="AdaptiveSRE — Theory of Mind Benchmark",
        theme=gr.themes.Base(),
        css="""
        .big-gauge { font-size: 64px !important; text-align: center; }
        .drift-flash { animation: flash 0.5s ease-in-out 3; }
        @keyframes flash { 0%,100% { opacity:1; } 50% { opacity:0.3; } }
        """,
    ) as demo:

        gr.Markdown("""
# 🔬 AdaptiveSRE — Theory of Mind in Agentic Systems
**The first RL benchmark with 2 simultaneous hidden states: infrastructure fault + hidden Lead Engineer priority.**

> *"Can the agent understand why fixing the server is suddenly the wrong move?"*
""")

        with gr.Row():
            with gr.Column(scale=2):
                gr.Markdown("### Episode Configuration")
                task_dropdown = gr.Dropdown(
                    choices=["easy", "medium", "hard"],
                    value="hard",
                    label="Task difficulty",
                )
                model_toggle = gr.Radio(
                    choices=["Gen 0 (Baseline — zero-shot)", "Gen 1 (GRPO Trained)"],
                    value="Gen 0 (Baseline — zero-shot)",
                    label="Agent model",
                )
                run_btn = gr.Button("▶  Run Episode", variant="primary", size="lg")

            with gr.Column(scale=3):
                # Alignment gauge — THE centrepiece
                gr.Markdown("### Alignment Score")
                alignment_display = gr.HTML(
                    value='<div style="text-align:center;padding:20px;color:#666;">Press Run to start</div>'
                )

        with gr.Row():
            with gr.Column():
                gr.Markdown("### Lead Mode")
                lead_mode_display = gr.HTML(
                    value='<div style="text-align:center;padding:16px;color:#666;">—</div>'
                )
            with gr.Column():
                gr.Markdown("### Drift Detection")
                drift_display = gr.HTML(
                    value='<div style="text-align:center;padding:12px;color:#666;">—</div>'
                )

        with gr.Row():
            status_text = gr.Textbox(label="Episode status", interactive=False)

        with gr.Row():
            with gr.Column():
                gr.Markdown("### Service Health")
                services_display = gr.Markdown("No data yet")
            with gr.Column():
                gr.Markdown("### Reward History")
                reward_display = gr.Textbox(
                    value="No data yet",
                    label="",
                    interactive=False,
                    lines=3,
                )

        with gr.Row():
            gr.Markdown("### Step-by-step Trajectory")
        trajectory_display = gr.Markdown("Episode not started")

        # Training results chart (shown if file exists)
        chart_path = Path("rewards_curve.png")
        if chart_path.exists():
            with gr.Row():
                gr.Markdown("### Training Results: Gen 0 vs Gen 1")
                gr.Image(str(chart_path), label="Reward improvement after GRPO training")

        gr.Markdown("""
---
### How to read this demo
1. **Services** degrade — DB goes red, auth/payment follow (cascade)
2. **Alignment score** rises as agent takes correct actions for the Lead mode
3. At a random step (8–14 in hard mode), Lead mode **silently shifts**
4. **Alignment score drops** — agent was correct for old mode, now wrong
5. Agent detects the reward pattern shift → **DRIFT DETECTED** fires
6. Agent pivots strategy → alignment **climbs back up**

*That recovery arc is what GRPO training teaches.*
""")

        # Wire up the button
        run_btn.click(
            fn=_run_demo_episode,
            inputs=[task_dropdown, model_toggle],
            outputs=[
                alignment_display,
                lead_mode_display,
                drift_display,
                services_display,
                reward_display,
                trajectory_display,
                status_text,
            ],
        )

    return demo


# ── Mount Gradio on FastAPI ────────────────────────────────────────────────
gradio_app = build_gradio_ui()
app = gr.mount_gradio_app(app, gradio_app, path="/")


def main():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)


if __name__ == "__main__":
    main()