"""
Expectation suite đơn giản (không bắt buộc Great Expectations).

Sinh viên có thể thay bằng GE / pydantic / custom — miễn là có halt có kiểm soát.

Sprint 2 — expectation mới:
  E7) no_future_effective_date (halt)  — double-check R8: không chunk nào có ngày > hôm nay.
  E8) no_invalid_exported_at (warn)    — cảnh báo nếu chunk có exported_at rỗng/sai format.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Tuple

TODAY_ISO: str = date.today().isoformat()
_EXPORTED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


@dataclass
class ExpectationResult:
    name: str
    passed: bool
    severity: str  # "warn" | "halt"
    detail: str


def run_expectations(cleaned_rows: List[Dict[str, Any]]) -> Tuple[List[ExpectationResult], bool]:
    """
    Trả về (results, should_halt).

    should_halt = True nếu có bất kỳ expectation severity halt nào fail.
    """
    results: List[ExpectationResult] = []

    # E1: có ít nhất 1 dòng sau clean
    ok = len(cleaned_rows) >= 1
    results.append(ExpectationResult("min_one_row", ok, "halt", f"cleaned_rows={len(cleaned_rows)}"))

    # E2: không doc_id rỗng
    bad_doc = [r for r in cleaned_rows if not (r.get("doc_id") or "").strip()]
    results.append(ExpectationResult("no_empty_doc_id", len(bad_doc) == 0, "halt", f"empty_doc_id_count={len(bad_doc)}"))

    # E3: policy refund không được chứa cửa sổ sai 14 ngày (sau khi đã fix)
    bad_refund = [
        r for r in cleaned_rows
        if r.get("doc_id") == "policy_refund_v4" and "14 ngày làm việc" in (r.get("chunk_text") or "")
    ]
    results.append(ExpectationResult("refund_no_stale_14d_window", len(bad_refund) == 0, "halt", f"violations={len(bad_refund)}"))

    # E4: chunk_text đủ dài
    short = [r for r in cleaned_rows if len((r.get("chunk_text") or "")) < 8]
    results.append(ExpectationResult("chunk_min_length_8", len(short) == 0, "warn", f"short_chunks={len(short)}"))

    # E5: effective_date đúng định dạng ISO sau clean (phát hiện parser lỏng)
    iso_bad = [
        r for r in cleaned_rows
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", (r.get("effective_date") or "").strip())
    ]
    results.append(ExpectationResult("effective_date_iso_yyyy_mm_dd", len(iso_bad) == 0, "halt", f"non_iso_rows={len(iso_bad)}"))

    # E6: không còn marker phép năm cũ 10 ngày trên doc HR (conflict version sau clean)
    bad_hr_annual = [
        r for r in cleaned_rows
        if r.get("doc_id") == "hr_leave_policy" and "10 ngày phép năm" in (r.get("chunk_text") or "")
    ]
    results.append(ExpectationResult("hr_leave_no_stale_10d_annual", len(bad_hr_annual) == 0, "halt", f"violations={len(bad_hr_annual)}"))

    # E7 (Sprint 2): không chunk nào có effective_date trong tương lai — safety net cho R8.
    # severity=halt: chunk ngày tương lai = policy chưa phát hành lọt vào production index.
    future_rows = [r for r in cleaned_rows if (r.get("effective_date") or "") > TODAY_ISO]
    results.append(
        ExpectationResult(
            "no_future_effective_date",
            len(future_rows) == 0,
            "halt",
            f"future_dated_rows={len(future_rows)} today={TODAY_ISO}",
        )
    )

    # E8 (Sprint 2): mọi chunk phải có exported_at hợp lệ (ISO datetime).
    # severity=warn: thiếu exported_at không chặn pipeline nhưng làm freshness check sai.
    bad_exported = [
        r for r in cleaned_rows
        if not _EXPORTED_AT_RE.match((r.get("exported_at") or "").strip())
    ]
    results.append(
        ExpectationResult(
            "no_invalid_exported_at",
            len(bad_exported) == 0,
            "warn",
            f"invalid_exported_at_count={len(bad_exported)}",
        )
    )

    halt = any(not r.passed and r.severity == "halt" for r in results)
    return results, halt
