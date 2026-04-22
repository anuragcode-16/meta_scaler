from fastapi import FastAPI
from pydantic import BaseModel
import asyncio
import random

app = FastAPI(title="Payment Service (Mock)")

state = {
    "health": 1.0,
    "latency_ms": 55.0,
    "error_rate": 0.0,
    "cpu_pct": 18.0,
    "transactions_per_sec": 124,
    "pending_transactions": 23
}

class HealthResponse(BaseModel):
    status: str
    health: float
    latency_ms: float
    error_rate: float
    cpu_pct: float
    transactions_per_sec: int
    pending_transactions: int
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
        transactions_per_sec=state["transactions_per_sec"],
        pending_transactions=state["pending_transactions"],
        port=8101
    )

@app.get("/stats")
async def stats():
    cpu = random.uniform(state["cpu_pct"] - 5, state["cpu_pct"] + 10)
    mem_used = random.uniform(192, 384)
    mem_limit = 2048
    mem_pct = (mem_used / mem_limit) * 100
    net_in = random.uniform(1.0, 3.0)
    net_out = random.uniform(0.5, 1.5)
    return f"""CONTAINER    CPU%    MEM/LIMIT       MEM%    NET I/O
payment-svc  {cpu:5.1f}%   {mem_used:6.0f}MiB/{mem_limit}MiB    {mem_pct:5.1f}%   {net_in:.1f}MB/{net_out:.1f}MB"""

@app.post("/crash")
async def crash():
    state["health"] = 0.1
    state["error_rate"] = 0.9
    state["latency_ms"] = random.uniform(800, 3000)
    state["cpu_pct"] = random.uniform(85, 99)
    state["transactions_per_sec"] = random.randint(0, 10)
    state["pending_transactions"] = random.randint(500, 1000)
    return {"status": "crashed", "health": state["health"]}

@app.post("/recover")
async def recover():
    state["health"] = 1.0
    state["error_rate"] = 0.0
    state["latency_ms"] = random.uniform(20, 80)
    state["cpu_pct"] = random.uniform(10, 25)
    state["transactions_per_sec"] = random.randint(100, 200)
    state["pending_transactions"] = random.randint(10, 50)
    return {"status": "recovered", "health": state["health"]}

@app.get("/logs")
async def logs():
    if state["error_rate"] > 0.5:
        return """2026-04-22 14:23:11.234 ERROR [payment] Transaction processing failed - auth service 503
Traceback (most recent call last):
  File "/app/payment/processor.py", line 201, in process_transaction
    auth_valid = await self.auth.validate(token)
  File "/app/payment/auth_client.py", line 78, in validate
    raise ServiceUnavailableError("Auth service returned 503")
payment.errors.ServiceUnavailableError: Auth service returned 503

2026-04-22 14:23:11.456 ERROR [payment] Transaction txn_9a8b7c6d failed: timeout after 2500ms
2026-04-22 14:23:11.567 ERROR [payment] Payment gateway connection reset by peer
2026-04-22 14:23:12.001 WARN  [payment] Transaction queue depth: 847 (threshold: 100)"""
    else:
        return """2026-04-22 14:22:45.123 INFO  [payment] GET /health 200 55ms
2026-04-22 14:22:46.234 INFO  [payment] Transaction processed: txn_9a8b7c6d ($149.99)
2026-04-22 14:22:47.345 INFO  [payment] Gateway response: APPROVED (auth_code: 847291)
2026-04-22 14:22:48.456 INFO  [payment] TPS (last 60s): 124
2026-04-22 14:22:49.567 INFO  [payment] Pending transactions: 23"""
