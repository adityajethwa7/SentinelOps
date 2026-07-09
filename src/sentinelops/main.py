"""FastAPI application — SentinelOps entry point."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(
    title="SentinelOps",
    description="Confidence-Driven Autonomous SRE Remediation Agent",
    version="1.0.0",
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "sentinelops"}
