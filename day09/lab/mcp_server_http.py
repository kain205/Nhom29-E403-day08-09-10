"""
mcp_server_http.py — Real MCP HTTP Server (Sprint 3 Bonus)
FastAPI server expose MCP tools qua HTTP.

Endpoints:
    GET  /tools          → list available tools (discovery)
    POST /tools/call     → execute a tool

Chạy server:
    uvicorn mcp_server_http:app --host 0.0.0.0 --port 8080 --reload

Test:
    curl http://localhost:8080/tools
    curl -X POST http://localhost:8080/tools/call \
         -H "Content-Type: application/json" \
         -d '{"tool": "get_ticket_info", "input": {"ticket_id": "P1-LATEST"}}'
"""

import os
import sys
from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Reuse all tool logic from the existing mock server
sys.path.insert(0, os.path.dirname(__file__))
from mcp_server import dispatch_tool, list_tools

app = FastAPI(
    title="Day09 MCP Server",
    description="MCP-compatible HTTP server for Day 09 lab tools",
    version="1.0.0",
)


# ─────────────────────────────────────────────
# Request / Response models
# ─────────────────────────────────────────────

class ToolCallRequest(BaseModel):
    tool: str
    input: dict = {}


class ToolCallResponse(BaseModel):
    tool: str
    output: dict
    error: dict | None = None
    timestamp: str


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@app.get("/tools")
def get_tools():
    """MCP tool discovery — trả về danh sách tools và schema."""
    return {"tools": list_tools()}


@app.post("/tools/call", response_model=ToolCallResponse)
def call_tool(body: ToolCallRequest):
    """MCP tool execution — gọi tool theo tên và input."""
    result = dispatch_tool(body.tool, body.input)

    error = None
    if isinstance(result, dict) and "error" in result:
        error = {"message": result["error"]}

    return ToolCallResponse(
        tool=body.tool,
        output=result,
        error=error,
        timestamp=datetime.now().isoformat(),
    )


@app.get("/health")
def health():
    return {"status": "ok", "server": "day09-mcp", "timestamp": datetime.now().isoformat()}
