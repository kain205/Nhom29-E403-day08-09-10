import json, os

traces_dir = "artifacts/traces"
files = [f for f in sorted(os.listdir(traces_dir)) if f.endswith(".json")]

for fname in files:
    with open(os.path.join(traces_dir, fname), encoding="utf-8") as f:
        t = json.load(f)
    qid = t.get("question_id", "?")
    task = t.get("task", "")[:65]
    route = t.get("supervisor_route", "?")
    conf = t.get("confidence", 0)
    hitl = t.get("hitl_triggered", False)
    policy = t.get("policy_result", {})
    exceptions = policy.get("exceptions_found", [])
    llm_used = policy.get("llm_used", False)
    policy_applies = policy.get("policy_applies", "N/A")
    answer = t.get("final_answer", "")[:150]
    mcp = t.get("mcp_tools_used", [])
    sources = t.get("retrieved_sources", [])

    print(f"--- {qid} ---")
    print(f"  task: {task}")
    print(f"  route: {route} | conf: {conf} | hitl: {hitl}")
    print(f"  policy_applies: {policy_applies} | exceptions: {len(exceptions)} | llm_used: {llm_used}")
    if exceptions:
        for ex in exceptions:
            print(f"    exception: {ex.get('type')} — {ex.get('rule','')[:60]}")
    print(f"  sources: {sources}")
    print(f"  mcp_calls: {len(mcp)}")
    print(f"  answer: {answer}")
    print()
