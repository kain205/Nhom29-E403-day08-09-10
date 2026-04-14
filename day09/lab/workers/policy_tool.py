"""
workers/policy_tool.py — Policy & Tool Worker
Sprint 2+3: Kiểm tra policy dựa vào context, gọi MCP tools khi cần.

Input (từ AgentState):
    - task: câu hỏi
    - retrieved_chunks: context từ retrieval_worker
    - needs_tool: True nếu supervisor quyết định cần tool call

Output (vào AgentState):
    - policy_result: {"policy_applies", "policy_name", "exceptions_found", "source", "rule"}
    - mcp_tools_used: list of tool calls đã thực hiện
    - worker_io_log: log

Gọi độc lập để test:
    python workers/policy_tool.py
"""

import os
import sys
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

WORKER_NAME = "policy_tool_worker"

POLICY_ANALYSIS_PROMPT = """Bạn là chuyên gia phân tích chính sách nội bộ.

Dựa vào context tài liệu được cung cấp, hãy phân tích câu hỏi và trả lời theo JSON format sau:
{
  "policy_applies": true/false/null,
  "policy_name": "tên chính sách áp dụng",
  "exceptions_found": [
    {"type": "tên_exception", "rule": "mô tả rule", "source": "tên file"}
  ],
  "reasoning": "giải thích ngắn gọn tại sao policy áp dụng hoặc không",
  "policy_version_note": "ghi chú nếu có vấn đề về version/thời gian hiệu lực",
  "ambiguous": true/false,
  "ambiguous_reason": "lý do nếu trường hợp phức tạp/mơ hồ",
  "needs_more_info": {
    "required": true/false,
    "tool": "tên MCP tool cần gọi hoặc null",
    "tool_input": {"key": "value"},
    "reason": "tại sao cần thêm thông tin"
  }
}

Quy tắc:
- CHỈ dựa vào context được cung cấp, không dùng kiến thức ngoài.
- Nếu task là câu hỏi thông tin (không phải request cụ thể) → policy_applies=null, exceptions_found=[].
- Nếu không đủ thông tin để quyết định → policy_applies=null, ambiguous=true.
- exceptions_found CHỈ chứa lý do policy TỪ CHỐI request (không được hoàn tiền, không được cấp quyền).
- KHÔNG liệt kê SLA rules, escalation procedures, quy trình xử lý vào exceptions_found.
- Nếu policy_version_note có nội dung VÀ không có tài liệu của version đó trong context → policy_applies=null, ambiguous=true. KHÔNG được kết luận dựa trên version sai.
- Nếu task liên quan đến cấp quyền access level cụ thể (level 1/2/3) → ưu tiên gọi "check_access_permission" để xác nhận emergency bypass, KHÔNG dùng "get_ticket_info" cho mục đích này.
- Nếu cần thông tin real-time (ticket status, access permission) → set needs_more_info.required=true.
  Dùng đúng tên tool và tên parameter từ danh sách MCP TOOLS AVAILABLE được cung cấp trong message.
- Trả về JSON thuần túy, không markdown.
"""


def _get_mcp_tool_schemas() -> str:
    """Fetch tool schemas từ MCP server để inject vào LLM prompt."""
    try:
        from mcp_server import list_tools
        tools = list_tools()
        lines = ["=== MCP TOOLS AVAILABLE ==="]
        for t in tools:
            schema = t.get("inputSchema", {})
            props = schema.get("properties", {})
            required = schema.get("required", [])
            params = []
            for k, v in props.items():
                req = "(required)" if k in required else "(optional)"
                params.append(f"    {k}: {v.get('type')} {req} — {v.get('description', '')}")
            lines.append(f"Tool: {t['name']}")
            lines.append(f"  Description: {t['description']}")
            lines.append("  Parameters:")
            lines.extend(params)
        return "\n".join(lines)
    except Exception:
        return ""


def _call_llm_policy(task: str, chunks: list) -> dict:
    """
    Gọi OpenAI để phân tích policy phức tạp dựa trên context chunks.
    Returns parsed dict hoặc None nếu thất bại.
    """
    import json

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source", "unknown")
        text = chunk.get("text", "")
        context_parts.append(f"[{i}] {source}:\n{text}")
    context = "\n\n".join(context_parts) if context_parts else "(Không có tài liệu)"

    tool_schemas = _get_mcp_tool_schemas()

    user_message = f"""Câu hỏi: {task}

=== TÀI LIỆU THAM KHẢO ===
{context}

{tool_schemas}

Phân tích và trả về JSON."""

    # Option A: OpenAI
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": POLICY_ANALYSIS_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        return json.loads(raw)
    except Exception as e:
        print(f"[policy_tool] OpenAI call failed: {e}")

    # Option B: Gemini fallback
    try:
        import google.generativeai as genai
        import re
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        model = genai.GenerativeModel("gemini-1.5-flash")
        combined = POLICY_ANALYSIS_PROMPT + "\n\n" + user_message
        response = model.generate_content(combined)
        text = response.text
        # Strip markdown code fences if present
        text = re.sub(r"```(?:json)?", "", text).strip()
        return json.loads(text)
    except Exception as e:
        print(f"[policy_tool] Gemini call failed: {e}")

    return None


# ─────────────────────────────────────────────
# MCP Client — Sprint 3: Thay bằng real MCP call
# ─────────────────────────────────────────────

def _coerce_tool_input(tool_name: str, tool_input: dict) -> dict:
    """Ép kiểu input cho đúng schema, phòng LLM trả về string thay vì int/bool."""
    if tool_name == "check_access_permission":
        if "access_level" in tool_input:
            tool_input["access_level"] = int(tool_input["access_level"])
        if "is_emergency" in tool_input and isinstance(tool_input["is_emergency"], str):
            tool_input["is_emergency"] = tool_input["is_emergency"].lower() == "true"
    if tool_name == "search_kb" and "top_k" in tool_input:
        tool_input["top_k"] = int(tool_input["top_k"])
    return tool_input


def _call_mcp_tool(tool_name: str, tool_input: dict) -> dict:
    """
    Gọi MCP tool.
    - MCP_SERVER_MODE=http  → gọi HTTP server tại MCP_SERVER_URL
    - MCP_SERVER_MODE=mock  → gọi trực tiếp dispatch_tool() trong-process
    """
    from datetime import datetime

    mode = os.getenv("MCP_SERVER_MODE", "mock").lower()
    timestamp = datetime.now().isoformat()

    if mode == "http":
        try:
            import httpx
            url = os.getenv("MCP_SERVER_URL", "http://localhost:8080")
            resp = httpx.post(
                f"{url}/tools/call",
                json={"tool": tool_name, "input": tool_input},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "tool": tool_name,
                "input": tool_input,
                "output": data.get("output"),
                "error": data.get("error"),
                "timestamp": timestamp,
            }
        except Exception as e:
            return {
                "tool": tool_name,
                "input": tool_input,
                "output": None,
                "error": {"code": "MCP_HTTP_FAILED", "reason": str(e)},
                "timestamp": timestamp,
            }
    else:
        # mock mode: in-process call
        try:
            from mcp_server import dispatch_tool
            result = dispatch_tool(tool_name, tool_input)
            return {
                "tool": tool_name,
                "input": tool_input,
                "output": result,
                "error": None,
                "timestamp": timestamp,
            }
        except Exception as e:
            return {
                "tool": tool_name,
                "input": tool_input,
                "output": None,
                "error": {"code": "MCP_CALL_FAILED", "reason": str(e)},
                "timestamp": timestamp,
            }


# ─────────────────────────────────────────────
# Policy Analysis Logic
# ─────────────────────────────────────────────

def analyze_policy(task: str, chunks: list) -> dict:
    """
    Phân tích policy dựa trên context chunks bằng LLM.
    Nếu LLM xác định cần thêm thông tin → gọi MCP tool → phân tích lại.

    Returns:
        dict with: policy_applies, policy_name, exceptions_found, source, explanation, llm_used
    """
    sources = list({c.get("source", "unknown") for c in chunks if c})

    if not chunks:
        return {
            "policy_applies": None,
            "policy_name": "unknown",
            "exceptions_found": [],
            "source": [],
            "policy_version_note": "",
            "explanation": "Không có context để phân tích policy.",
            "llm_used": False,
            "ambiguous": True,
        }

    # --- Round 1: LLM phân tích với chunks hiện có ---
    llm_result = _call_llm_policy(task, chunks)

    if not llm_result:
        return {
            "policy_applies": None,
            "policy_name": "unknown",
            "exceptions_found": [],
            "source": sources,
            "policy_version_note": "",
            "explanation": "LLM call failed — cannot determine policy.",
            "llm_used": False,
            "ambiguous": True,
        }

    # --- Round 2: Nếu LLM cần thêm thông tin → gọi MCP ---
    mcp_extra = []
    needs_more = llm_result.get("needs_more_info", {})
    if needs_more.get("required") and needs_more.get("tool"):
        tool_name = needs_more["tool"]
        tool_input = _coerce_tool_input(tool_name, needs_more.get("tool_input", {}))
        mcp_result = _call_mcp_tool(tool_name, tool_input)
        mcp_extra.append(mcp_result)

        if mcp_result.get("output") and not mcp_result.get("error"):
            # Thêm MCP output vào chunks dưới dạng synthetic chunk
            mcp_chunk = {
                "text": f"[MCP {tool_name}] " + str(mcp_result["output"]),
                "source": f"mcp:{tool_name}",
                "score": 1.0,
            }
            enriched_chunks = chunks + [mcp_chunk]

            # Phân tích lại với context đầy đủ hơn
            llm_result2 = _call_llm_policy(task, enriched_chunks)
            if llm_result2:
                llm_result = llm_result2
                sources = list({c.get("source", "unknown") for c in enriched_chunks if c})

    exceptions_found = llm_result.get("exceptions_found", [])
    policy_applies = llm_result.get("policy_applies", None)
    if policy_applies is None:
        policy_applies = len(exceptions_found) == 0 if exceptions_found else None

    return {
        "policy_applies": policy_applies,
        "policy_name": llm_result.get("policy_name", "unknown"),
        "exceptions_found": exceptions_found,
        "source": sources,
        "policy_version_note": llm_result.get("policy_version_note", ""),
        "explanation": llm_result.get("reasoning", ""),
        "llm_used": True,
        "ambiguous": llm_result.get("ambiguous", False),
        "mcp_calls_made": mcp_extra,
    }


# ─────────────────────────────────────────────
# Worker Entry Point
# ─────────────────────────────────────────────

def run(state: dict) -> dict:
    """
    Worker entry point — gọi từ graph.py.

    Args:
        state: AgentState dict

    Returns:
        Updated AgentState với policy_result và mcp_tools_used
    """
    task = state.get("task", "")
    chunks = state.get("retrieved_chunks", [])
    needs_tool = state.get("needs_tool", False)

    state.setdefault("workers_called", [])
    state.setdefault("history", [])
    state.setdefault("mcp_tools_used", [])

    state["workers_called"].append(WORKER_NAME)

    worker_io = {
        "worker": WORKER_NAME,
        "input": {
            "task": task,
            "chunks_count": len(chunks),
            "needs_tool": needs_tool,
        },
        "output": None,
        "error": None,
    }

    try:
        # Step 1: Nếu chưa có chunks, gọi MCP search_kb
        if not chunks and needs_tool:
            mcp_result = _call_mcp_tool("search_kb", {"query": task, "top_k": 3})
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(f"[{WORKER_NAME}] called MCP search_kb")

            if mcp_result.get("output") and mcp_result["output"].get("chunks"):
                chunks = mcp_result["output"]["chunks"]
                state["retrieved_chunks"] = chunks

        # Step 2: Phân tích policy
        policy_result = analyze_policy(task, chunks)
        state["policy_result"] = policy_result

        # Merge MCP calls từ analyze_policy vào state
        for mcp_call in policy_result.pop("mcp_calls_made", []):
            state["mcp_tools_used"].append(mcp_call)
            state["history"].append(f"[{WORKER_NAME}] called MCP {mcp_call.get('tool')} (policy enrichment)")

        # Step 3: Nếu cần thêm info từ MCP (e.g., ticket status), gọi get_ticket_info
        if needs_tool and any(kw in task.lower() for kw in ["ticket", "p1", "jira"]):
            mcp_result = _call_mcp_tool("get_ticket_info", {"ticket_id": "P1-LATEST"})
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(f"[{WORKER_NAME}] called MCP get_ticket_info")

        worker_io["output"] = {
            "policy_applies": policy_result["policy_applies"],
            "exceptions_count": len(policy_result.get("exceptions_found", [])),
            "mcp_calls": len(state["mcp_tools_used"]),
        }
        state["history"].append(
            f"[{WORKER_NAME}] policy_applies={policy_result['policy_applies']}, "
            f"exceptions={len(policy_result.get('exceptions_found', []))}"
        )

    except Exception as e:
        worker_io["error"] = {"code": "POLICY_CHECK_FAILED", "reason": str(e)}
        state["policy_result"] = {"error": str(e)}
        state["history"].append(f"[{WORKER_NAME}] ERROR: {e}")

    state.setdefault("worker_io_logs", []).append(worker_io)
    return state


# ─────────────────────────────────────────────
# Test độc lập
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Policy Tool Worker — Standalone Test")
    print("=" * 50)

    test_cases = [
        {
            "task": "Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?",
            "retrieved_chunks": [
                {"text": "Ngoại lệ: Đơn hàng Flash Sale không được hoàn tiền.", "source": "policy_refund_v4.txt", "score": 0.9}
            ],
        },
        {
            "task": "Khách hàng muốn hoàn tiền license key đã kích hoạt.",
            "retrieved_chunks": [
                {"text": "Sản phẩm kỹ thuật số (license key, subscription) không được hoàn tiền.", "source": "policy_refund_v4.txt", "score": 0.88}
            ],
        },
        {
            "task": "Khách hàng yêu cầu hoàn tiền trong 5 ngày, sản phẩm lỗi, chưa kích hoạt.",
            "retrieved_chunks": [
                {"text": "Yêu cầu trong 7 ngày làm việc, sản phẩm lỗi nhà sản xuất, chưa dùng.", "source": "policy_refund_v4.txt", "score": 0.85}
            ],
        },
    ]

    for tc in test_cases:
        print(f"\n▶ Task: {tc['task'][:70]}...")
        result = run(tc.copy())
        pr = result.get("policy_result", {})
        print(f"  policy_applies: {pr.get('policy_applies')}")
        print(f"  llm_used: {pr.get('llm_used')} | ambiguous: {pr.get('ambiguous')}")
        if pr.get("exceptions_found"):
            for ex in pr["exceptions_found"]:
                print(f"  exception: {ex['type']} — {ex['rule'][:60]}...")
        if pr.get("explanation"):
            print(f"  reasoning: {pr['explanation'][:100]}")
        print(f"  MCP calls: {len(result.get('mcp_tools_used', []))}")

    print("\n✅ policy_tool_worker test done.")
