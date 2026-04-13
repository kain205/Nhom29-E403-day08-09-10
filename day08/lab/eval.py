"""
eval.py — Sprint 4: Evaluation & Scorecard
==========================================
Mục tiêu Sprint 4 (60 phút):
  - Chạy 10 test questions qua pipeline
  - Chấm điểm theo 4 metrics: Faithfulness, Relevance, Context Recall, Completeness
  - So sánh baseline vs variant
  - Ghi kết quả ra scorecard

Definition of Done Sprint 4:
  ✓ Demo chạy end-to-end (index → retrieve → answer → score)
  ✓ Scorecard trước và sau tuning
  ✓ A/B comparison: baseline vs variant với giải thích vì sao variant tốt hơn

A/B Rule (từ slide):
  Chỉ đổi MỘT biến mỗi lần để biết điều gì thực sự tạo ra cải thiện.
  Đổi đồng thời chunking + hybrid + rerank + prompt = không biết biến nào có tác dụng.

Evaluation Method: LLM-as-Judge
================================
Tất cả 4 metrics đều được chấm tự động bằng LLM (gpt-4o-mini, temperature=0).
Mỗi câu hỏi gọi 4 lần LLM judge riêng biệt — một lần cho mỗi metric.

  score_faithfulness()    — LLM chấm: answer có bám context không? (1-5)
  score_answer_relevance() — LLM chấm: answer có trả lời đúng câu hỏi không? (1-5)
  score_context_recall()  — Rule-based: expected source có trong retrieved chunks không?
  score_completeness()    — LLM chấm: answer có đủ key points so với expected không? (1-5)

Prompt judge format (JSON output):
  {"score": <int 1-5>, "reason": "<one sentence>"}

Lý do chọn LLM-as-Judge thay vì chấm thủ công:
  - Scalable: 10 câu × 5 configs × 4 metrics = 200 evaluations, không thể chấm tay
  - Consistent: temperature=0 cho output ổn định
  - Explainable: mỗi score kèm reason để debug
"""

import json
import csv
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv
from rag_answer import rag_answer

load_dotenv()

# =============================================================================
# CẤU HÌNH
# =============================================================================

TEST_QUESTIONS_PATH = Path(__file__).parent / "data" / "test_questions.json"
RESULTS_DIR = Path(__file__).parent / "results"

# Cấu hình baseline (Sprint 2)
BASELINE_CONFIG = {
    "retrieval_mode": "dense",
    "top_k_search": 10,
    "top_k_select": 3,
    "use_rerank": False,
    "prompt_version": "v1",
    "label": "baseline_dense",
}

# Variant 1 — Sprint 3: Hybrid retrieval (BM25 + RRF)
VARIANT1_CONFIG = {
    "retrieval_mode": "hybrid",   # dense_weight=0.6, sparse_weight=0.4, RRF k=60
    "top_k_search": 10,
    "top_k_select": 3,
    "use_rerank": False,
    "prompt_version": "v1",       # Prompt giữ nguyên — biến duy nhất thay đổi là retrieval_mode
    "label": "variant1_hybrid",
}

# Variant 2 — Sprint 3: Nuanced abstain prompt (3-tier)
VARIANT2_CONFIG = {
    "retrieval_mode": "dense",
    "top_k_search": 10,
    "top_k_select": 3,
    "use_rerank": False,
    "prompt_version": "v3",       # Prompt mới — biến duy nhất thay đổi là prompt_version
    "label": "variant2_nuanced_abstain",
}

# Variant 3 — prompt v2 + hybrid retrieval
VARIANT3_CONFIG = {
    "retrieval_mode": "hybrid",
    "top_k_search": 10,
    "top_k_select": 3,
    "use_rerank": False,
    "prompt_version": "v3",
    "label": "variant3_hybrid_nuanced",
}

# Variant 4 — prompt v2 + hybrid + rerank (cross-encoder)
VARIANT4_CONFIG = {
    "retrieval_mode": "hybrid",
    "top_k_search": 10,
    "top_k_select": 3,
    "use_rerank": True,
    "prompt_version": "v3",
    "label": "variant4_hybrid_rerank",
}

# Danh sách tất cả configs để chạy và so sánh
ALL_CONFIGS = [BASELINE_CONFIG, VARIANT1_CONFIG, VARIANT2_CONFIG, VARIANT3_CONFIG, VARIANT4_CONFIG]

# Map tên ngắn → config (dùng cho --run flag)
CONFIG_MAP = {
    "baseline": BASELINE_CONFIG,
    "variant1": VARIANT1_CONFIG,
    "variant2": VARIANT2_CONFIG,
    "variant3": VARIANT3_CONFIG,
    "variant4": VARIANT4_CONFIG,
}


# =============================================================================
# SCORING FUNCTIONS
# 4 metrics từ slide: Faithfulness, Answer Relevance, Context Recall, Completeness
# =============================================================================

ABSTAIN_PHRASE = "Không đủ dữ liệu để trả lời câu hỏi này."


def score_faithfulness(
    answer: str,
    chunks_used: List[Dict[str, Any]],
    expected_abstain: bool = False,
) -> Dict[str, Any]:
    """
    Faithfulness: Câu trả lời có bám đúng chứng cứ đã retrieve không?
    Câu hỏi: Model có tự bịa thêm thông tin ngoài retrieved context không?

    Thang điểm 1-5:
      5: Mọi thông tin trong answer đều có trong retrieved chunks
      4: Gần như hoàn toàn grounded, 1 chi tiết nhỏ chưa chắc chắn
      3: Phần lớn grounded, một số thông tin có thể từ model knowledge
      2: Nhiều thông tin không có trong retrieved chunks
      1: Câu trả lời không grounded, phần lớn là model bịa

    TODO Sprint 4 — Có 2 cách chấm:

    Cách 1 — Chấm thủ công (Manual, đơn giản):
        Đọc answer và chunks_used, chấm điểm theo thang trên.
        Ghi lý do ngắn gọn vào "notes".

    Cách 2 — LLM-as-Judge (Tự động, nâng cao):
        Gửi prompt cho LLM:
            "Given these retrieved chunks: {chunks}
             And this answer: {answer}
             Rate the faithfulness on a scale of 1-5.
             5 = completely grounded in the provided context.
             1 = answer contains information not in the context.
             Output JSON: {'score': <int>, 'reason': '<string>'}"

    Trả về dict với: score (1-5) và notes (lý do)
    """
    # Scorer bug fix: correct abstain should not be penalized
    if expected_abstain and ABSTAIN_PHRASE in answer:
        return {"score": 5, "notes": "Correct abstain — no source exists for this question"}

    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    context_text = "\n\n".join(c.get("text", "") for c in chunks_used)
    prompt = f"""You are an evaluator. Rate the faithfulness of the answer below on a scale of 1-5.
5 = every claim in the answer is fully supported by the retrieved context.
1 = the answer contains mostly fabricated information not in the context.

Retrieved context:
{context_text[:2000]}

Answer:
{answer}

Respond ONLY with valid JSON: {{"score": <int 1-5>, "reason": "<one sentence>"}}"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=100,
        )
        result = json.loads(resp.choices[0].message.content)
        return {"score": result["score"], "notes": result.get("reason", "")}
    except Exception as e:
        return {"score": None, "notes": f"LLM judge error: {e}"}


def score_answer_relevance(
    query: str,
    answer: str,
    expected_abstain: bool = False,
) -> Dict[str, Any]:
    """
    Answer Relevance: Answer có trả lời đúng câu hỏi người dùng hỏi không?
    Câu hỏi: Model có bị lạc đề hay trả lời đúng vấn đề cốt lõi không?

    Thang điểm 1-5:
      5: Answer trả lời trực tiếp và đầy đủ câu hỏi
      4: Trả lời đúng nhưng thiếu vài chi tiết phụ
      3: Trả lời có liên quan nhưng chưa đúng trọng tâm
      2: Trả lời lạc đề một phần
      1: Không trả lời câu hỏi

    TODO Sprint 4: Implement tương tự score_faithfulness
    """
    # Scorer bug fix: correct abstain should not be penalized
    if expected_abstain and ABSTAIN_PHRASE in answer:
        return {"score": 5, "notes": "Correct abstain — no source exists for this question"}

    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    prompt = f"""You are an evaluator. Rate how well the answer addresses the question on a scale of 1-5.
5 = answer directly and completely addresses the question.
1 = answer is completely irrelevant or does not address the question at all.

Question: {query}
Answer: {answer}

Respond ONLY with valid JSON: {{"score": <int 1-5>, "reason": "<one sentence>"}}"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=100,
        )
        result = json.loads(resp.choices[0].message.content)
        return {"score": result["score"], "notes": result.get("reason", "")}
    except Exception as e:
        return {"score": None, "notes": f"LLM judge error: {e}"}


def score_context_recall(
    chunks_used: List[Dict[str, Any]],
    expected_sources: List[str],
) -> Dict[str, Any]:
    """
    Context Recall: Retriever có mang về đủ evidence cần thiết không?
    Câu hỏi: Expected source có nằm trong retrieved chunks không?

    Đây là metric đo retrieval quality, không phải generation quality.

    Cách tính đơn giản:
        recall = (số expected source được retrieve) / (tổng số expected sources)

    Ví dụ:
        expected_sources = ["policy/refund-v4.pdf", "sla-p1-2026.pdf"]
        retrieved_sources = ["policy/refund-v4.pdf", "helpdesk-faq.md"]
        recall = 1/2 = 0.5

    TODO Sprint 4:
    1. Lấy danh sách source từ chunks_used
    2. Kiểm tra xem expected_sources có trong retrieved sources không
    3. Tính recall score
    """
    if not expected_sources:
        # Câu hỏi không có expected source (ví dụ: "Không đủ dữ liệu" cases)
        return {"score": None, "recall": None, "notes": "No expected sources"}

    retrieved_sources = {
        c.get("metadata", {}).get("source", "")
        for c in chunks_used
    }

    # TODO: Kiểm tra matching theo partial path (vì source paths có thể khác format)
    found = 0
    missing = []
    for expected in expected_sources:
        # Kiểm tra partial match (tên file)
        expected_name = expected.split("/")[-1].replace(".pdf", "").replace(".md", "")
        matched = any(expected_name.lower() in r.lower() for r in retrieved_sources)
        if matched:
            found += 1
        else:
            missing.append(expected)

    recall = found / len(expected_sources) if expected_sources else 0

    return {
        "score": round(recall * 5),  # Convert to 1-5 scale
        "recall": recall,
        "found": found,
        "missing": missing,
        "notes": f"Retrieved: {found}/{len(expected_sources)} expected sources" +
                 (f". Missing: {missing}" if missing else ""),
    }


def score_completeness(
    query: str,
    answer: str,
    expected_answer: str,
) -> Dict[str, Any]:
    """
    Completeness: Answer có thiếu điều kiện ngoại lệ hoặc bước quan trọng không?
    Câu hỏi: Answer có bao phủ đủ thông tin so với expected_answer không?

    Thang điểm 1-5:
      5: Answer bao gồm đủ tất cả điểm quan trọng trong expected_answer
      4: Thiếu 1 chi tiết nhỏ
      3: Thiếu một số thông tin quan trọng
      2: Thiếu nhiều thông tin quan trọng
      1: Thiếu phần lớn nội dung cốt lõi

    TODO Sprint 4:
    Option 1 — Chấm thủ công: So sánh answer vs expected_answer và chấm.
    Option 2 — LLM-as-Judge:
        "Compare the model answer with the expected answer.
         Rate completeness 1-5. Are all key points covered?
         Output: {'score': int, 'missing_points': [str]}"
    """
    if not expected_answer:
        return {"score": None, "notes": "No expected answer provided"}

    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    prompt = f"""You are an evaluator. Compare the model answer against the expected answer and rate completeness on a scale of 1-5.
5 = all key points from the expected answer are covered.
1 = most key points are missing.

Question: {query}
Expected answer: {expected_answer}
Model answer: {answer}

Respond ONLY with valid JSON: {{"score": <int 1-5>, "reason": "<one sentence>"}}"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=100,
        )
        result = json.loads(resp.choices[0].message.content)
        return {"score": result["score"], "notes": result.get("reason", "")}
    except Exception as e:
        return {"score": None, "notes": f"LLM judge error: {e}"}


# =============================================================================
# SCORECARD RUNNER
# =============================================================================

def run_scorecard(
    config: Dict[str, Any],
    test_questions: Optional[List[Dict]] = None,
    verbose: bool = True,
) -> List[Dict[str, Any]]:
    """
    Chạy toàn bộ test questions qua pipeline và chấm điểm.

    Args:
        config: Pipeline config (retrieval_mode, top_k, use_rerank, ...)
        test_questions: List câu hỏi (load từ JSON nếu None)
        verbose: In kết quả từng câu

    Returns:
        List scorecard results, mỗi item là một row

    TODO Sprint 4:
    1. Load test_questions từ data/test_questions.json
    2. Với mỗi câu hỏi:
       a. Gọi rag_answer() với config tương ứng
       b. Chấm 4 metrics
       c. Lưu kết quả
    3. Tính average scores
    4. In bảng kết quả
    """
    if test_questions is None:
        with open(TEST_QUESTIONS_PATH, "r", encoding="utf-8") as f:
            test_questions = json.load(f)

    results = []
    label = config.get("label", "unnamed")

    print(f"\n{'='*70}")
    print(f"Chạy scorecard: {label}")
    print(f"Config: {config}")
    print('='*70)

    for q in test_questions:
        question_id = q["id"]
        query = q["question"]
        expected_answer = q.get("expected_answer", "")
        expected_sources = q.get("expected_sources", [])
        expected_abstain = q.get("expected_abstain", False)
        category = q.get("category", "")

        if verbose:
            print(f"\n[{question_id}] {query}")

        # --- Gọi pipeline ---
        try:
            result = rag_answer(
                query=query,
                retrieval_mode=config.get("retrieval_mode", "dense"),
                top_k_search=config.get("top_k_search", 10),
                top_k_select=config.get("top_k_select", 3),
                use_rerank=config.get("use_rerank", False),
                prompt_version=config.get("prompt_version", "v1"),
                verbose=False,
            )
            answer = result["answer"]
            chunks_used = result["chunks_used"]

        except NotImplementedError:
            answer = "PIPELINE_NOT_IMPLEMENTED"
            chunks_used = []
        except Exception as e:
            answer = f"ERROR: {e}"
            chunks_used = []

        # --- Chấm điểm ---
        faith = score_faithfulness(answer, chunks_used, expected_abstain=expected_abstain)
        relevance = score_answer_relevance(query, answer, expected_abstain=expected_abstain)
        recall = score_context_recall(chunks_used, expected_sources)
        complete = score_completeness(query, answer, expected_answer)

        row = {
            "id": question_id,
            "category": category,
            "query": query,
            "answer": answer,
            "expected_answer": expected_answer,
            "faithfulness": faith["score"],
            "faithfulness_notes": faith["notes"],
            "relevance": relevance["score"],
            "relevance_notes": relevance["notes"],
            "context_recall": recall["score"],
            "context_recall_notes": recall["notes"],
            "completeness": complete["score"],
            "completeness_notes": complete["notes"],
            "config_label": label,
        }
        results.append(row)

        if verbose:
            print(f"  Answer: {answer[:100]}...")
            print(f"  Faithful: {faith['score']} | Relevant: {relevance['score']} | "
                  f"Recall: {recall['score']} | Complete: {complete['score']}")

    # Tính averages (bỏ qua None)
    for metric in ["faithfulness", "relevance", "context_recall", "completeness"]:
        scores = [r[metric] for r in results if r[metric] is not None]
        avg = sum(scores) / len(scores) if scores else None
        print(f"\nAverage {metric}: {avg:.2f}" if avg else f"\nAverage {metric}: N/A (chưa chấm)")

    return results


# =============================================================================
# A/B COMPARISON
# =============================================================================

def compare_ab(
    results_by_label: Dict[str, List[Dict]],
    output_csv: Optional[str] = None,
) -> None:
    """
    So sánh N configs cạnh nhau theo metric và per-question.

    Args:
        results_by_label: {"baseline_dense": [...], "variant1_hybrid": [...], ...}
        output_csv: tên file CSV để lưu, None = không lưu
    """
    metrics = ["faithfulness", "relevance", "context_recall", "completeness"]
    labels = list(results_by_label.keys())
    col_w = 12

    print(f"\n{'='*80}")
    print("Comparison: " + " vs ".join(labels))
    print('='*80)

    # --- Average scores ---
    avgs: Dict[str, Dict[str, Any]] = {}
    for label, rows in results_by_label.items():
        avgs[label] = {}
        for m in metrics:
            scores = [r[m] for r in rows if r.get(m) is not None]
            avgs[label][m] = sum(scores) / len(scores) if scores else None

    # Header
    header = f"{'Metric':<22}" + "".join(f"{lb:>{col_w}}" for lb in labels)
    # Delta columns vs baseline (first label)
    baseline_label = labels[0]
    for lb in labels[1:]:
        header += f"  Δ{lb[:8]:>8}"
    print(header)
    print("-" * len(header))

    for m in metrics:
        row = f"{m:<22}"
        for lb in labels:
            val = avgs[lb][m]
            row += f"{(f'{val:.2f}') if val is not None else 'N/A':>{col_w}}"
        for lb in labels[1:]:
            b_val = avgs[baseline_label][m]
            v_val = avgs[lb][m]
            if b_val is not None and v_val is not None:
                d = v_val - b_val
                row += f"  {d:>+8.2f}"
            else:
                row += f"  {'N/A':>8}"
        print(row)

    # --- Per-question ---
    print(f"\n{'Câu':<6}", end="")
    for lb in labels:
        print(f"  {lb[:18]:<20}", end="")
    print(f"  {'Best':<12}")
    print("-" * (6 + len(labels) * 22 + 14))

    # Collect all question ids from first label
    all_rows_by_id: Dict[str, Dict[str, Any]] = {}
    for label, rows in results_by_label.items():
        for r in rows:
            qid = r["id"]
            if qid not in all_rows_by_id:
                all_rows_by_id[qid] = {}
            all_rows_by_id[qid][label] = r

    for qid in sorted(all_rows_by_id.keys()):
        print(f"{qid:<6}", end="")
        totals = {}
        for lb in labels:
            r = all_rows_by_id[qid].get(lb, {})
            score_str = "/".join(str(r.get(m, "?")) for m in metrics)
            totals[lb] = sum(r.get(m, 0) or 0 for m in metrics)
            print(f"  {score_str:<20}", end="")
        best = max(totals, key=lambda lb: totals[lb])
        all_same = len(set(totals.values())) == 1
        print(f"  {'Tie' if all_same else best:<12}")

    # --- Export CSV (all configs combined) ---
    if output_csv:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        csv_path = RESULTS_DIR / output_csv
        all_rows = [r for rows in results_by_label.values() for r in rows]
        if all_rows:
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
                writer.writeheader()
                writer.writerows(all_rows)
            print(f"\nKết quả đã lưu vào: {csv_path}")


# =============================================================================
# REPORT GENERATOR
# =============================================================================

def generate_scorecard_summary(results: List[Dict], label: str) -> str:
    """
    Tạo báo cáo tóm tắt scorecard dạng markdown.

    TODO Sprint 4: Cập nhật template này theo kết quả thực tế của nhóm.
    """
    metrics = ["faithfulness", "relevance", "context_recall", "completeness"]
    averages = {}
    for metric in metrics:
        scores = [r[metric] for r in results if r[metric] is not None]
        averages[metric] = sum(scores) / len(scores) if scores else None

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    md = f"""# Scorecard: {label}
Generated: {timestamp}

## Summary

| Metric | Average Score |
|--------|--------------|
"""
    for metric, avg in averages.items():
        avg_str = f"{avg:.2f}/5" if avg else "N/A"
        md += f"| {metric.replace('_', ' ').title()} | {avg_str} |\n"

    md += "\n## Per-Question Results\n\n"
    md += "| ID | Category | Faithful | Relevant | Recall | Complete | Notes |\n"
    md += "|----|----------|----------|----------|--------|----------|-------|\n"

    for r in results:
        md += (f"| {r['id']} | {r['category']} | {r.get('faithfulness', 'N/A')} | "
               f"{r.get('relevance', 'N/A')} | {r.get('context_recall', 'N/A')} | "
               f"{r.get('completeness', 'N/A')} | {r.get('faithfulness_notes', '')[:50]} |\n")

    return md


# =============================================================================
# MAIN — Chạy evaluation
# =============================================================================

def _save_scorecard(results: List[Dict], config: Dict) -> Path:
    """Lưu scorecard ra file theo label, trả về path."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    label = config["label"]

    # Save markdown summary
    md = generate_scorecard_summary(results, label)
    path = RESULTS_DIR / f"scorecard_{label}.md"
    path.write_text(md, encoding="utf-8")
    print(f"Scorecard lưu tại: {path}")

    # Save full CSV with answers (for later merging)
    csv_path = RESULTS_DIR / f"scorecard_{label}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    return path


def _load_results_from_csv(csv_path: Path) -> Dict[str, List[Dict]]:
    """Load kết quả đã lưu từ ab_comparison CSV, trả về dict label → rows."""
    results: Dict[str, List[Dict]] = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for m in ["faithfulness", "relevance", "context_recall", "completeness"]:
            r[m] = int(r[m]) if r.get(m) and r[m] not in ("", "None") else None
        label = r["config_label"]
        results.setdefault(label, []).append(r)
    return results


if __name__ == "__main__":
    import argparse

    valid_run_choices = ["all", "compare"] + list(CONFIG_MAP.keys())

    parser = argparse.ArgumentParser(
        description="RAG Evaluation Scorecard",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--run",
        choices=valid_run_choices,
        default="all",
        help=(
            "all        — chạy tất cả configs rồi compare (default)\n"
            "baseline   — chỉ chạy baseline_dense\n"
            "variant1   — chỉ chạy variant1_hybrid\n"
            "variant2   — chỉ chạy variant2_nuanced_abstain\n"
            "variant3   — chỉ chạy variant3_hybrid_nuanced\n"
            "variant4   — chỉ chạy variant4_hybrid_rerank\n"
            "compare    — load CSV đã lưu và in bảng so sánh (không gọi API)\n"
        ),
    )
    args = parser.parse_args()

    print("=" * 60)
    print(f"Sprint 4: Evaluation & Scorecard  [--run {args.run}]")
    print("=" * 60)

    # Load test questions
    print(f"\nLoading test questions từ: {TEST_QUESTIONS_PATH}")
    try:
        with open(TEST_QUESTIONS_PATH, "r", encoding="utf-8") as f:
            test_questions = json.load(f)
        print(f"Tìm thấy {len(test_questions)} câu hỏi")
        for q in test_questions[:3]:
            print(f"  [{q['id']}] {q['question']} ({q['category']})")
        print("  ...")
    except FileNotFoundError:
        print("Không tìm thấy file test_questions.json!")
        test_questions = []

    AB_CSV = "ab_comparison_all.csv"
    results_by_label: Dict[str, List[Dict]] = {}

    if args.run == "compare":
        # Load từ CSV đã lưu, không chạy lại pipeline
        csv_path = RESULTS_DIR / AB_CSV
        if not csv_path.exists():
            print(f"Chưa có {AB_CSV} — chạy --run all trước.")
        else:
            results_by_label = _load_results_from_csv(csv_path)
    elif args.run == "all":
        configs_to_run = ALL_CONFIGS
    else:
        configs_to_run = [CONFIG_MAP[args.run]]

    if args.run != "compare":
        for config in configs_to_run:
            print(f"\n--- Chạy: {config['label']} ---")
            try:
                res = run_scorecard(config=config, test_questions=test_questions, verbose=True)
                _save_scorecard(res, config)
                results_by_label[config["label"]] = res
            except NotImplementedError:
                print(f"Pipeline chưa implement cho config: {config['label']}")

    # --- So sánh nếu có từ 2 configs trở lên ---
    if len(results_by_label) >= 2:
        compare_ab(results_by_label, output_csv=AB_CSV)
    elif len(results_by_label) == 1:
        print("\n(Chỉ có 1 config — bỏ qua compare. Chạy --run all để so sánh.)")
