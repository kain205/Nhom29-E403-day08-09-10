# AI in Action — Nhóm 29 · E403

**Course:** AI in Action – Phase 1 · VinUniversity 2026
**Repo:** RAG → Multi-Agent → Data Pipeline (Day 08 · 09 · 10)

| Thành viên | MSSV |
|------------|------|
| Nguyễn Bình Thành | 2A202600138 |
| Hàn Quang Hiếu | 2A202600056 |

---

## Day 08 — RAG Pipeline

| | |
|---|---|
| **Hệ thống** | RAG pipeline cho trợ lý nội bộ CS + IT Helpdesk — heading-based chunking (29 chunks / 5 tài liệu), OpenAI `text-embedding-3-small` + ChromaDB, `gpt-4o-mini` temperature=0 |
| **Variants** | Baseline → V1 Hybrid BM25+RRF → V2 Hybrid+Prompt v3 → V3 Prompt only → **V4 Hybrid+Rerank** (config được chọn) |
| **Scorecard (V4)** | Faithfulness=5.00 · Answer Relevance=5.00 · Context Recall=5.00 · Completeness=4.80 |
| **Key finding** | Prompt engineering (3-tier abstain logic) tăng Completeness +0.90; hybrid BM25 gây noise ngược khi dense đã recall tốt |
| **Docs** | [Lab README](day08/lab/README.md) · [Group Report](day08/lab/reports/group_report.md) · [IndividualReport1](day08/lab/reports/individual/NguyenBinhThanh.md) · [IndividualReport2](day08/lab/reports/individual/han_quang_hieu.md) · [SCORING](day08/lab/SCORING.md) |

---

## Day 09 — Multi-Agent Orchestration

| | |
|---|---|
| **Hệ thống** | Supervisor + 3 workers (retrieval, policy\_tool, synthesis) · MCP server với 4 tools · HTTP server bonus (FastAPI) |
| **Grading** | **87 / 96 raw → ~27.2 / 30 điểm** (judge: `claude-sonnet-4-6`) |
| **Điểm mạnh** | gq02, gq07 abstain đúng — không hallucinate khi thiếu tài liệu |
| **Điểm yếu** | gq01, gq09 thiếu kết luận "escalate → Senior Engineer" trong SLA flow |
| **Docs** | [Lab README](day09/lab/README.md) · [Group Report](day09/lab/reports/group_report.md) · [IndividualReport1](day09/lab/reports/individual/NguyenBinhThanh.md) · [IndividualReport2](day09/lab/reports/individual/han_quang_hieu.md) · [Grading log](day09/lab/artifacts/grading_run.jsonl) |

---

## Day 10 — Data Pipeline & Observability

| | |
|---|---|
| **Hệ thống** | ETL pipeline: raw CSV → cleaning rules (R1–R9) → expectation suite (E1–E8) → embed ChromaDB (upsert + prune) → manifest → freshness check |
| **UI** | Streamlit demo app (`day10/lab/app.py`) — 4 tab × 4 sprint; chạy: `streamlit run day10/lab/app.py` |
| **Inject** | `--no-refund-fix --skip-validate` → expectation FAIL + `embed_prune_removed=1` → retrieval `hits_forbidden=yes` → restore |
| **Freshness** | SLA 24h — FAIL (age=121h, file mẫu cố định 2026-04-10, expected) |
| **Docs** | [Lab README](day10/lab/README.md) · [Group Report](day10/lab/reports/group_report.md) · [IndividualReport1](day10/lab/reports/individual/NguyenBinhThanh.md) · [IndividualReport2](day10/lab/reports/individual/han_quang_hieu.md) |
