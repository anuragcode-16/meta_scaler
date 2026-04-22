from fastapi import FastAPI
from pydantic import BaseModel
import asyncio
import random

app = FastAPI(title="DB Service (PostgreSQL Mock)")

state = {
    "health": 1.0,
    "latency_ms": 45.0,
    "error_rate": 0.0,
    "cpu_pct": 12.0,
    "connection_pool_used": 5,
    "connection_pool_max": 100
}

class HealthResponse(BaseModel):
    status: str
    health: float
    latency_ms: float
    error_rate: float
    cpu_pct: float
    connection_pool_used: int
    connection_pool_max: int
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
        connection_pool_used=state["connection_pool_used"],
        connection_pool_max=state["connection_pool_max"],
        port=15432
    )

@app.get("/stats")
async def stats():
    cpu = random.uniform(state["cpu_pct"] - 5, state["cpu_pct"] + 10)
    mem_used = random.uniform(256, 512)
    mem_limit = 2048
    mem_pct = (mem_used / mem_limit) * 100
    net_in = random.uniform(0.5, 2.0)
    net_out = random.uniform(0.2, 0.8)
    return f"""CONTAINER    CPU%    MEM/LIMIT       MEM%    NET I/O
db-svc       {cpu:5.1f}%   {mem_used:6.0f}MiB/{mem_limit}MiB    {mem_pct:5.1f}%   {net_in:.1f}MB/{net_out:.1f}MB"""

@app.post("/crash")
async def crash():
    state["health"] = 0.1
    state["error_rate"] = 0.9
    state["latency_ms"] = random.uniform(800, 3000)
    state["cpu_pct"] = random.uniform(85, 99)
    state["connection_pool_used"] = state["connection_pool_max"]
    return {"status": "crashed", "health": state["health"]}

@app.post("/recover")
async def recover():
    state["health"] = 1.0
    state["error_rate"] = 0.0
    state["latency_ms"] = random.uniform(20, 80)
    state["cpu_pct"] = random.uniform(10, 25)
    state["connection_pool_used"] = random.randint(3, 15)
    return {"status": "recovered", "health": state["health"]}

@app.get("/logs")
async def logs():
    if state["error_rate"] > 0.5:
        return """2026-04-22 14:23:11.234 ERROR [db] Connection pool exhausted - max connections reached
Traceback (most recent call last):
  File "/app/db/connection.py", line 142, in acquire
    conn = self.pool.get(timeout=5.0)
  File "/usr/local/lib/python3.11/site-packages/psycopg2/pool.py", line 167, in get
    raise PoolError("connection pool exhausted")
psycopg2.pool.PoolError: connection pool exhausted

2026-04-22 14:23:11.456 ERROR [db] Failed to execute query: SELECT * FROM users WHERE id=$1
2026-04-22 14:23:11.567 ERROR [db] Transaction rollback due to connection failure
2026-04-22 14:23:12.001 WARN  [db] Retry attempt 3/5 for connection acquisition"""
    else:
        return """2026-04-22 14:22:45.123 INFO  [db] GET /health 200 45ms
2026-04-22 14:22:46.234 INFO  [db] GET /stats 200 12ms
2026-04-22 14:22:47.345 INFO  [db] Query executed: SELECT * FROM config LIMIT 1 (23ms)
2026-04-22 14:22:48.456 INFO  [db] Connection pool: 5/100 active
2026-04-22 14:22:49.567 INFO  [db] Checkpoint completed in 124ms"""
