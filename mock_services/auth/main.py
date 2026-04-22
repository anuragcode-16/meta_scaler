from fastapi import FastAPI
from pydantic import BaseModel
import asyncio
import random

app = FastAPI(title="Auth Service (Mock)")

state = {
    "health": 1.0,
    "latency_ms": 35.0,
    "error_rate": 0.0,
    "cpu_pct": 15.0,
    "auth_failures_per_min": 12,
    "active_sessions": 847
}

class HealthResponse(BaseModel):
    status: str
    health: float
    latency_ms: float
    error_rate: float
    cpu_pct: float
    auth_failures_per_min: int
    active_sessions: int
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
        auth_failures_per_min=state["auth_failures_per_min"],
        active_sessions=state["active_sessions"],
        port=8102
    )

@app.get("/stats")
async def stats():
    cpu = random.uniform(state["cpu_pct"] - 5, state["cpu_pct"] + 10)
    mem_used = random.uniform(128, 256)
    mem_limit = 1024
    mem_pct = (mem_used / mem_limit) * 100
    net_in = random.uniform(0.3, 1.2)
    net_out = random.uniform(0.1, 0.5)
    return f"""CONTAINER    CPU%    MEM/LIMIT       MEM%    NET I/O
auth-svc     {cpu:5.1f}%   {mem_used:6.0f}MiB/{mem_limit}MiB    {mem_pct:5.1f}%   {net_in:.1f}MB/{net_out:.1f}MB"""

@app.post("/crash")
async def crash():
    state["health"] = 0.1
    state["error_rate"] = 0.9
    state["latency_ms"] = random.uniform(800, 3000)
    state["cpu_pct"] = random.uniform(85, 99)
    state["auth_failures_per_min"] = random.randint(500, 1000)
    return {"status": "crashed", "health": state["health"]}

@app.post("/recover")
async def recover():
    state["health"] = 1.0
    state["error_rate"] = 0.0
    state["latency_ms"] = random.uniform(20, 80)
    state["cpu_pct"] = random.uniform(10, 25)
    state["auth_failures_per_min"] = random.randint(5, 20)
    return {"status": "recovered", "health": state["health"]}

@app.get("/logs")
async def logs():
    if state["error_rate"] > 0.5:
        return """2026-04-22 14:23:11.234 ERROR [auth] Token validation failed - upstream DB connection timeout
Traceback (most recent call last):
  File "/app/auth/validator.py", line 89, in validate_token
    user = await self.db.get_user(token.user_id)
  File "/app/auth/database.py", line 156, in get_user
    raise ConnectionTimeoutError("Database connection pool exhausted")
auth.errors.ConnectionTimeoutError: Database connection pool exhausted

2026-04-22 14:23:11.456 ERROR [auth] Authentication failed for user_id=usr_847291
2026-04-22 14:23:11.567 ERROR [auth] Session invalidation cascade triggered
2026-04-22 14:23:12.001 WARN  [auth] Rate limiting activated: 847 failures in last 60s"""
    else:
        return """2026-04-22 14:22:45.123 INFO  [auth] GET /health 200 35ms
2026-04-22 14:22:46.234 INFO  [auth] Token validated: usr_847291 (expires in 23m)
2026-04-22 14:22:47.345 INFO  [auth] Session created: sess_9a8b7c6d (TTL: 3600s)
2026-04-22 14:22:48.456 INFO  [auth] Active sessions: 847
2026-04-22 14:22:49.567 INFO  [auth] Auth failures (last 60s): 12"""
