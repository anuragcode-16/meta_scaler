from fastapi import FastAPI
from pydantic import BaseModel
import asyncio
import random

app = FastAPI(title="Notification Service (Mock)")

state = {
    "health": 1.0,
    "latency_ms": 42.0,
    "error_rate": 0.0,
    "cpu_pct": 10.0,
    "queue_depth": 127,
    "messages_per_sec": 89
}

class HealthResponse(BaseModel):
    status: str
    health: float
    latency_ms: float
    error_rate: float
    cpu_pct: float
    queue_depth: int
    messages_per_sec: int
    port: int

@app.get("/health", response_model=HealthResponse)
async def health():
    await asyncio.sleep(state["latency_ms"] / 1000)
    status = "healthy" if state["health"] > 0.8 else "degraded" if state["health"] > 0.3 else "critical"
    return HealthResponse(
        status=status,
        health=state["health"],
        latency_ms=state["latency_ms"],
        error_rate=state["error_rate"],
        cpu_pct=state["cpu_pct"],
        queue_depth=state["queue_depth"],
        messages_per_sec=state["messages_per_sec"],
        port=8103
    )

@app.get("/stats")
async def stats():
    cpu = random.uniform(state["cpu_pct"] - 3, state["cpu_pct"] + 5)
    mem_used = random.uniform(96, 160)
    mem_limit = 512
    mem_pct = (mem_used / mem_limit) * 100
    net_in = random.uniform(0.2, 0.8)
    net_out = random.uniform(0.5, 1.5)
    return f"""CONTAINER    CPU%    MEM/LIMIT       MEM%    NET I/O
notif-svc    {cpu:5.1f}%   {mem_used:6.0f}MiB/{mem_limit}MiB    {mem_pct:5.1f}%   {net_in:.1f}MB/{net_out:.1f}MB"""

@app.post("/crash")
async def crash():
    state["health"] = 0.1
    state["error_rate"] = 0.9
    state["latency_ms"] = random.uniform(800, 3000)
    state["cpu_pct"] = random.uniform(85, 99)
    state["queue_depth"] = random.randint(5000, 10000)
    state["messages_per_sec"] = random.randint(0, 5)
    return {"status": "crashed", "health": state["health"]}

@app.post("/recover")
async def recover():
    state["health"] = 1.0
    state["error_rate"] = 0.0
    state["latency_ms"] = random.uniform(20, 60)
    state["cpu_pct"] = random.uniform(5, 15)
    state["queue_depth"] = random.randint(50, 200)
    state["messages_per_sec"] = random.randint(50, 150)
    return {"status": "recovered", "health": state["health"]}

@app.get("/logs")
async def logs():
    if state["error_rate"] > 0.5:
        return """2026-04-22 14:23:11.234 ERROR [notification] Message delivery failed - queue overflow
Traceback (most recent call last):
  File "/app/notification/dispatcher.py", line 89, in dispatch
    await self.queue.push(message)
  File "/app/notification/queue.py", line 156, in push
    raise QueueOverflowError("Queue depth exceeds maximum threshold")
notification.errors.QueueOverflowError: Queue depth exceeds maximum threshold

2026-04-22 14:23:11.456 ERROR [notification] Failed to send email: smtp.connection_refused
2026-04-22 14:23:11.567 ERROR [notification] Webhook delivery failed: upstream timeout
2026-04-22 14:23:12.001 WARN  [notification] Queue depth: 8471 (threshold: 500)"""
    else:
        return """2026-04-22 14:22:45.123 INFO  [notification] GET /health 200 42ms
2026-04-22 14:22:46.234 INFO  [notification] Email sent: usr_847291 (order_confirmation)
2026-04-22 14:22:47.345 INFO  [notification] Webhook delivered: payment.completed (23ms)
2026-04-22 14:22:48.456 INFO  [notification] Queue depth: 127
2026-04-22 14:22:49.567 INFO  [notification] Messages/sec (last 60s): 89"""