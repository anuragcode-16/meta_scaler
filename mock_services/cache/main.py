from fastapi import FastAPI
from pydantic import BaseModel
import asyncio
import random

app = FastAPI(title="Cache Service (Redis Mock)")

state = {
    "health": 1.0,
    "latency_ms": 8.0,
    "error_rate": 0.0,
    "cpu_pct": 8.0,
    "hit_rate": 0.94,
    "memory_used_mb": 512,
    "keys_count": 15847
}

class HealthResponse(BaseModel):
    status: str
    health: float
    latency_ms: float
    error_rate: float
    cpu_pct: float
    hit_rate: float
    memory_used_mb: int
    keys_count: int
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
        hit_rate=state["hit_rate"],
        memory_used_mb=state["memory_used_mb"],
        keys_count=state["keys_count"],
        port=6379
    )

@app.get("/stats")
async def stats():
    cpu = random.uniform(state["cpu_pct"] - 3, state["cpu_pct"] + 5)
    mem_used = random.uniform(480, 540)
    mem_limit = 1024
    mem_pct = (mem_used / mem_limit) * 100
    net_in = random.uniform(0.8, 2.0)
    net_out = random.uniform(0.4, 1.0)
    return f"""CONTAINER    CPU%    MEM/LIMIT       MEM%    NET I/O
cache-svc    {cpu:5.1f}%   {mem_used:6.0f}MiB/{mem_limit}MiB    {mem_pct:5.1f}%   {net_in:.1f}MB/{net_out:.1f}MB"""

@app.post("/crash")
async def crash():
    state["health"] = 0.1
    state["error_rate"] = 0.9
    state["latency_ms"] = random.uniform(800, 3000)
    state["cpu_pct"] = random.uniform(85, 99)
    state["hit_rate"] = random.uniform(0.1, 0.3)
    return {"status": "crashed", "health": state["health"]}

@app.post("/recover")
async def recover():
    state["health"] = 1.0
    state["error_rate"] = 0.0
    state["latency_ms"] = random.uniform(5, 15)
    state["cpu_pct"] = random.uniform(5, 15)
    state["hit_rate"] = random.uniform(0.90, 0.98)
    return {"status": "recovered", "health": state["health"]}

@app.get("/logs")
async def logs():
    if state["error_rate"] > 0.5:
        return """2026-04-22 14:23:11.234 ERROR [cache] Memory eviction failed - OOM killer invoked
Traceback (most recent call last):
  File "/app/cache/store.py", line 142, in set
    self._evict_if_needed()
  File "/app/cache/store.py", line 198, in _evict_if_needed
    raise MemoryError("Cannot evict keys - memory pressure critical")
cache.errors.MemoryError: Cannot evict keys - memory pressure critical

2026-04-22 14:23:11.456 ERROR [cache] Key lookup failed: session:usr_847291 (not found, expected cached)
2026-04-22 14:23:11.567 ERROR [cache] Connection to replica redis-2 lost
2026-04-22 14:23:12.001 WARN  [cache] Hit rate dropped to 23% (normal: 94%)"""
    else:
        return """2026-04-22 14:22:45.123 INFO  [cache] GET /health 200 8ms
2026-04-22 14:22:46.234 INFO  [cache] Cache hit: session:usr_847291 (TTL: 1847s)
2026-04-22 14:22:47.345 INFO  [cache] Cache miss: config:feature_flags (fetching from DB)
2026-04-22 14:22:48.456 INFO  [cache] Hit rate (last 60s): 94%
2026-04-22 14:22:49.567 INFO  [cache] Keys: 15847, Memory: 512MiB"""
