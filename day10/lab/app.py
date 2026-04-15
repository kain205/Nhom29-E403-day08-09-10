#!/usr/bin/env python3
"""
Lab Day 10 — Demo UI
Run: cd day10/lab && streamlit run app.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

# ── Paths ──────────────────────────────────────────────────────────────────
LAB_DIR = Path(__file__).resolve().parent
RAW_CSV = LAB_DIR / "data" / "raw" / "policy_export_dirty.csv"
ART = LAB_DIR / "artifacts"
CLEAN_DIR = ART / "cleaned"
QUAR_DIR = ART / "quarantine"
MAN_DIR = ART / "manifests"
EVAL_DIR = ART / "eval"


# ── Helpers ────────────────────────────────────────────────────────────────

def _run_pipeline(run_id: str, *, no_refund_fix=False, skip_validate=False,
                  no_future_date_check=False, no_short_chunk_check=False,
                  no_empty_strip_check=False):
    cmd = [sys.executable, "etl_pipeline.py", "run", "--run-id", run_id]
    if no_refund_fix:
        cmd.append("--no-refund-fix")
    if skip_validate:
        cmd.append("--skip-validate")
    if no_future_date_check:
        cmd.append("--no-future-date-check")
    if no_short_chunk_check:
        cmd.append("--no-short-chunk-check")
    if no_empty_strip_check:
        cmd.append("--no-empty-strip-check")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(LAB_DIR))
    return r.stdout + ("\n" + r.stderr if r.stderr.strip() else ""), r.returncode


def _load_questions() -> dict:
    """Load test_questions.json → dict keyed by id."""
    p = LAB_DIR / "data" / "test_questions.json"
    if not p.is_file():
        return {}
    try:
        qs = json.loads(p.read_text("utf-8"))
        return {q["id"]: q for q in qs}
    except Exception:
        return {}


def _rich_eval_table(eval_path: Optional[Path]) -> None:
    """Bảng eval với cột expected + forbidden + kết quả màu."""
    df = _load_csv(eval_path)
    if df is None:
        st.info("Chưa có kết quả eval.")
        return

    questions = _load_questions()
    rows = []
    for _, r in df.iterrows():
        qid = r.get("question_id", "")
        q = questions.get(qid, {})
        must = ", ".join(q.get("must_contain_any", []))
        forbidden = ", ".join(q.get("must_not_contain", [])) or "—"
        ok = r.get("contains_expected", "")
        bad = r.get("hits_forbidden", "")
        top1_ok = r.get("top1_doc_expected", "")

        # Overall pass/fail
        passed = (ok == "yes") and (bad == "no")
        rows.append({
            "question_id": qid,
            "must contain": must,
            "forbidden": forbidden,
            "contains_expected": ok,
            "hits_forbidden": bad,
            "top1_doc_expected": top1_ok if top1_ok else "—",
            "top1_doc_id": r.get("top1_doc_id", ""),
            "result": "PASS" if passed else "FAIL",
        })

    result_df = pd.DataFrame(rows)

    def _color(row):
        if row["result"] == "PASS":
            return ["background-color: #e8f5e9"] * len(row)
        return ["background-color: #fde8e8"] * len(row)

    st.dataframe(
        result_df.style.apply(_color, axis=1),
        use_container_width=True,
        hide_index=True,
        column_config={
            "result": st.column_config.TextColumn("result", width="small"),
            "contains_expected": st.column_config.TextColumn("contains_expected", width="small"),
            "hits_forbidden": st.column_config.TextColumn("hits_forbidden", width="small"),
            "top1_doc_expected": st.column_config.TextColumn("top1_doc_expected", width="small"),
        },
    )


def _run_eval(out_name: str):
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out = EVAL_DIR / out_name
    r = subprocess.run(
        [sys.executable, "eval_retrieval.py", "--out", str(out)],
        capture_output=True, text=True, cwd=str(LAB_DIR),
    )
    return r.stdout + r.stderr, r.returncode, out


def _parse_expectations(stdout: str) -> list:
    out = []
    for line in stdout.splitlines():
        x = re.match(r"expectation\[(.+?)\] (OK|FAIL) \((.+?)\) :: (.+)", line)
        if x:
            out.append({
                "expectation": x.group(1),
                "status": x.group(2),
                "severity": x.group(3),
                "detail": x.group(4),
            })
    return out


def _parse_freshness(stdout: str) -> Optional[tuple]:
    for line in stdout.splitlines():
        if line.startswith("freshness_check="):
            _, rest = line.split("=", 1)
            parts = rest.split(" ", 1)
            status = parts[0]
            try:
                detail = json.loads(parts[1]) if len(parts) > 1 else {}
            except Exception:
                detail = {}
            return status, detail
    return None


def _load_csv(path) -> Optional[pd.DataFrame]:
    p = Path(path) if path else None
    if p and p.is_file():
        try:
            return pd.read_csv(p, dtype=str)
        except Exception:
            return None
    return None


def _load_manifest(run_id: str) -> Optional[dict]:
    safe = run_id.replace(":", "-")
    p = MAN_DIR / f"manifest_{safe}.json"
    if p.is_file():
        try:
            return json.loads(p.read_text("utf-8"))
        except Exception:
            return None
    return None


def _all_manifests() -> list:
    out = []
    for p in sorted(MAN_DIR.glob("manifest_*.json"),
                    key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            out.append(json.loads(p.read_text("utf-8")))
        except Exception:
            pass
    return out


# ── Reusable widgets ───────────────────────────────────────────────────────

def _pipeline_banner(stdout: str, rc: int) -> None:
    if "PIPELINE_OK" in stdout:
        st.success("PIPELINE_OK")
    elif "PIPELINE_HALT" in stdout:
        st.error("PIPELINE_HALT — expectation failed (halt)")
    elif rc != 0:
        st.error(f"Pipeline error (rc={rc})")


def _metrics_row(man: dict) -> None:
    raw = int(man.get("raw_records", 0) or 0)
    cleaned = int(man.get("cleaned_records", 0) or 0)
    quar = int(man.get("quarantine_records", 0) or 0)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Raw records", raw)
    c2.metric("Cleaned", cleaned, delta=str(cleaned - raw), delta_color="off")
    c3.metric("Quarantine", quar)
    c4.metric("Embed upsert", cleaned)


def _freshness_banner(status: str, detail: dict) -> None:
    age = detail.get("age_hours", "?")
    sla = detail.get("sla_hours", "?")
    msg = f"Freshness: {status} — data age **{age}h** / SLA **{sla}h**"
    if status == "PASS":
        st.success(msg)
    elif status == "WARN":
        st.warning(msg)
    else:
        st.warning(msg + "  _(file mẫu cũ sẵn — bình thường trong lab)_")


def _decision_table(raw_path: Path, quar_path: Optional[Path]) -> None:
    """Bảng tổng hợp: mỗi raw record + status Kept/Quarantine + reason."""
    df_raw = _load_csv(raw_path)
    if df_raw is None:
        return

    # Build lookup: chunk_id → reason từ quarantine CSV
    quar_map: dict = {}
    if quar_path and quar_path.is_file():
        df_q = _load_csv(quar_path)
        if df_q is not None and "chunk_id" in df_q.columns:
            for _, row in df_q.iterrows():
                quar_map[str(row["chunk_id"])] = row.get("reason", "quarantined")

    statuses, reasons = [], []
    for _, row in df_raw.iterrows():
        cid = str(row.get("chunk_id", ""))
        if cid in quar_map:
            statuses.append("Quarantine")
            reasons.append(quar_map[cid])
        else:
            statuses.append("Kept")
            reasons.append("")

    df_raw = df_raw.copy()
    df_raw.insert(0, "status", statuses)
    df_raw.insert(1, "reason", reasons)

    def _row_color(row):
        if row["status"] == "Quarantine":
            return ["background-color: #fde8e8"] * len(row)
        return ["background-color: #e8f5e9"] * len(row)

    st.dataframe(
        df_raw.style.apply(_row_color, axis=1),
        use_container_width=True,
        hide_index=True,
        column_config={
            "status": st.column_config.TextColumn("status", width="small"),
            "reason": st.column_config.TextColumn("reason", width="medium"),
        },
    )


def _show_expectations(stdout: str) -> None:
    exps = _parse_expectations(stdout)
    if not exps:
        return
    st.markdown("**Expectations**")
    df = pd.DataFrame(exps)
    st.dataframe(df, use_container_width=True, hide_index=True,
                 column_config={
                     "status": st.column_config.TextColumn(width="small"),
                     "severity": st.column_config.TextColumn(width="small"),
                 })


# ── Page ───────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Day 10 — Pipeline Demo",
    layout="wide",
    page_icon="📊",
)

st.title("Day 10 — Data Pipeline & Observability")
st.caption("ETL → Clean → Validate → Embed  ·  Sprint 1–4")

tab1, tab2, tab3, tab4 = st.tabs([
    "Sprint 1 — Ingest",
    "Sprint 2 — Clean + Validate",
    "Sprint 3 — Inject Corruption",
    "Sprint 4 — Monitoring",
])


# ─────────────────────────── SPRINT 1 ──────────────────────────────────────
with tab1:
    st.subheader("Sprint 1 — Ingest & Schema")
    st.markdown("Chạy pipeline chuẩn · raw → clean → quarantine → embed")

    c_ctrl, _ = st.columns([2, 4])
    with c_ctrl:
        s1_rid = st.text_input("run_id", "sprint1", key="s1_rid")
        if st.button("▶  Run Pipeline", key="s1_btn", type="primary"):
            with st.spinner("Loading model & running pipeline (first run ~15s)…"):
                stdout, rc = _run_pipeline(s1_rid)
            st.session_state.update(s1_stdout=stdout, s1_rc=rc, s1_rid_used=s1_rid)

    # If no run yet but artifact exists, offer auto-display from manifest
    if "s1_stdout" not in st.session_state:
        man = _load_manifest("sprint1")
        if man:
            st.info("Artifact **sprint1** đã có từ run trước — nhấn Run để chạy lại, "
                    "hoặc xem kết quả bên dưới.")
            st.session_state["s1_preloaded_man"] = man

    stdout = st.session_state.get("s1_stdout")
    rid_used = st.session_state.get("s1_rid_used", "sprint1")
    man = _load_manifest(rid_used) or st.session_state.get("s1_preloaded_man")

    if man:
        if stdout:
            _pipeline_banner(stdout, st.session_state.get("s1_rc", 0))

        _metrics_row(man)

        fresh = _parse_freshness(stdout) if stdout else None
        if fresh:
            _freshness_banner(*fresh)

        st.divider()
        safe = rid_used.replace(":", "-")
        quar_path = QUAR_DIR / f"quarantine_{safe}.csv"

        # Decision View — toàn bộ raw records + status màu
        st.markdown(
            f"**Decision View — {man.get('raw_records','?')} records**  "
            f"&nbsp; 🟢 Kept: {man.get('cleaned_records','?')}  "
            f"&nbsp; 🔴 Quarantine: {man.get('quarantine_records','?')}"
        )
        _decision_table(RAW_CSV, quar_path)

        st.divider()

        # Chi tiết Cleaned + Quarantine
        c_clean, c_quar = st.columns(2)

        with c_clean:
            st.markdown(f"**Cleaned — {man.get('cleaned_records', '?')} records**")
            df = _load_csv(CLEAN_DIR / f"cleaned_{safe}.csv")
            if df is not None:
                st.dataframe(df, use_container_width=True, height=280, hide_index=True)

        with c_quar:
            st.markdown(f"**Quarantine — {man.get('quarantine_records', '?')} records**")
            df = _load_csv(quar_path)
            if df is not None:
                show_cols = [c for c in ["chunk_id", "doc_id", "chunk_text", "reason"]
                             if c in df.columns]
                st.dataframe(df[show_cols] if show_cols else df,
                             use_container_width=True, height=280, hide_index=True)

        if stdout:
            st.divider()
            _show_expectations(stdout)
            with st.expander("Terminal log"):
                st.code(stdout, language="text")


# ─────────────────────────── SPRINT 2 ──────────────────────────────────────
with tab2:
    st.subheader("Sprint 2 — Clean + Validate + Embed")
    st.markdown(
        "Thêm **≥3 rule mới + ≥2 expectation mới** trong `cleaning_rules.py` và `expectations.py`, "
        "rồi chạy lại để xem metric_impact so với baseline."
    )

    c1, c2 = st.columns(2)
    with c1:
        s2_rid = st.text_input("run_id sprint này", "sprint2", key="s2_rid")
    with c2:
        s2_base = st.text_input("Baseline để so sánh", "sprint1", key="s2_base")

    if st.button("▶  Run Pipeline", key="s2_btn", type="primary"):
        with st.spinner("Running pipeline…"):
            stdout, rc = _run_pipeline(s2_rid)
        st.session_state.update(
            s2_stdout=stdout, s2_rc=rc,
            s2_rid_used=s2_rid, s2_base_used=s2_base,
        )

    stdout = st.session_state.get("s2_stdout")
    if stdout:
        rid = st.session_state.get("s2_rid_used", s2_rid)
        base = st.session_state.get("s2_base_used", s2_base)

        _pipeline_banner(stdout, st.session_state.get("s2_rc", 0))

        man_cur = _load_manifest(rid)
        man_base = _load_manifest(base)

        # Metric comparison table
        if man_cur and man_base:
            st.markdown("**metric_impact — baseline vs sprint hiện tại**")
            keys = ["raw_records", "cleaned_records", "quarantine_records"]
            rows = []
            for k in keys:
                bv = int(man_base.get(k, 0) or 0)
                cv = int(man_cur.get(k, 0) or 0)
                rows.append({
                    "metric": k,
                    f"baseline ({base})": bv,
                    f"current ({rid})": cv,
                    "Δ": f"{cv - bv:+d}",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        elif man_cur:
            _metrics_row(man_cur)

        st.divider()
        _show_expectations(stdout)

        safe = rid.replace(":", "-")
        c_left, c_right = st.columns(2)
        with c_left:
            n = man_cur.get("cleaned_records", "?") if man_cur else "?"
            st.markdown(f"**Cleaned — {n}**")
            df = _load_csv(CLEAN_DIR / f"cleaned_{safe}.csv")
            if df is not None:
                st.dataframe(df, use_container_width=True, height=250, hide_index=True)
        with c_right:
            n = man_cur.get("quarantine_records", "?") if man_cur else "?"
            st.markdown(f"**Quarantine — {n}**")
            df = _load_csv(QUAR_DIR / f"quarantine_{safe}.csv")
            if df is not None:
                st.dataframe(df, use_container_width=True, height=250, hide_index=True)

        with st.expander("Terminal log"):
            st.code(stdout, language="text")


# ─────────────────────────── SPRINT 3 ──────────────────────────────────────
with tab3:
    st.subheader("Sprint 3 — Inject Corruption & Before/After")
    st.markdown("Chạy 2 kịch bản → so sánh eval retrieval để chứng minh pipeline quan trọng.")

    c_left, c_right = st.columns(2)

    # ---- Clean side ----
    with c_left:
        st.markdown("### Clean pipeline")
        st.caption("Tất cả rule ON · validate ON")
        if st.button("▶  Run Clean + Eval", key="s3_clean_btn", type="primary"):
            with st.spinner("Pipeline clean…"):
                stdout_c, rc_c = _run_pipeline("s3-clean")
            with st.spinner("Eval retrieval…"):
                _, _, eval_path_c = _run_eval("s3_clean_eval.csv")
            st.session_state.update(
                s3_clean_stdout=stdout_c, s3_clean_rc=rc_c,
                s3_clean_eval=eval_path_c,
            )

        if "s3_clean_stdout" in st.session_state:
            sc = st.session_state["s3_clean_stdout"]
            _pipeline_banner(sc, st.session_state.get("s3_clean_rc", 0))
            man = _load_manifest("s3-clean")
            if man:
                cc1, cc2 = st.columns(2)
                cc1.metric("Cleaned", man.get("cleaned_records"))
                cc2.metric("Quarantine", man.get("quarantine_records"))
            st.markdown("**Eval**")
            _rich_eval_table(st.session_state.get("s3_clean_eval"))

    # ---- Inject side ----
    with c_right:
        st.markdown("### Inject — chọn rule muốn tắt")

        no_refund   = st.checkbox("Tắt: refund 14→7 fix", value=True,  key="inj_refund")
        no_future   = st.checkbox("Tắt: future_date check", value=False, key="inj_future")
        no_short    = st.checkbox("Tắt: chunk_too_short check", value=False, key="inj_short")
        no_empty    = st.checkbox("Tắt: empty_strip check", value=False, key="inj_empty")
        skip_val    = st.checkbox("Skip validate (halt)", value=True, key="inj_skipval")
        auto_restore = st.checkbox("Auto-restore DB sau khi eval xong", value=False, key="inj_restore")

        if st.button("▶  Run Inject + Eval", key="s3_inject_btn", type="secondary"):
            with st.spinner("Pipeline inject…"):
                stdout_i, rc_i = _run_pipeline(
                    "s3-inject",
                    no_refund_fix=no_refund,
                    skip_validate=skip_val,
                    no_future_date_check=no_future,
                    no_short_chunk_check=no_short,
                    no_empty_strip_check=no_empty,
                )
            with st.spinner("Eval retrieval…"):
                _, _, eval_path_i = _run_eval("s3_inject_eval.csv")
            st.session_state.update(
                s3_inject_stdout=stdout_i, s3_inject_rc=rc_i,
                s3_inject_eval=eval_path_i,
            )
            if auto_restore:
                with st.spinner("Auto-restoring DB…"):
                    _run_pipeline("s3-restore")
                st.session_state["s3_restored"] = True

        if "s3_inject_stdout" in st.session_state:
            si = st.session_state["s3_inject_stdout"]
            if "PIPELINE_OK" in si:
                st.success("Pipeline ran" + (" · DB restored" if st.session_state.get("s3_restored") else " · DB còn dirty"))
            elif "PIPELINE_HALT" in si:
                st.error("PIPELINE_HALT")
            man = _load_manifest("s3-inject")
            if man:
                cc1, cc2 = st.columns(2)
                cc1.metric("Cleaned", man.get("cleaned_records"))
                cc2.metric("Quarantine", man.get("quarantine_records"))
            st.markdown("**Eval**")
            _rich_eval_table(st.session_state.get("s3_inject_eval"))

        # Manual restore nếu không auto
        if "s3_inject_stdout" in st.session_state and not st.session_state.get("s3_restored"):
            st.warning("DB đang ở trạng thái dirty.", icon="⚠️")
            if st.button("↺  Restore DB thủ công", key="s3_restore_btn"):
                with st.spinner("Restoring…"):
                    _run_pipeline("s3-restore")
                st.session_state["s3_restored"] = True
                st.success("DB restored.")

    # ---- Before vs After comparison ----
    df_c = _load_csv(st.session_state.get("s3_clean_eval"))
    df_i = _load_csv(st.session_state.get("s3_inject_eval"))

    if df_c is not None and df_i is not None:
        st.divider()
        st.markdown("### Before vs After — so sánh trực tiếp")
        left = df_c[["question_id", "question", "contains_expected", "hits_forbidden"]].rename(
            columns={"contains_expected": "clean_ok", "hits_forbidden": "clean_bad"})
        right = df_i[["question_id", "contains_expected", "hits_forbidden"]].rename(
            columns={"contains_expected": "inject_ok", "hits_forbidden": "inject_bad"})
        comp = left.merge(right, on="question_id")
        st.dataframe(comp, use_container_width=True, hide_index=True)

    # Logs
    if "s3_clean_stdout" in st.session_state or "s3_inject_stdout" in st.session_state:
        with st.expander("Terminal logs"):
            if "s3_clean_stdout" in st.session_state:
                st.markdown("**Clean:**")
                st.code(st.session_state["s3_clean_stdout"], language="text")
            if "s3_inject_stdout" in st.session_state:
                st.markdown("**Inject:**")
                st.code(st.session_state["s3_inject_stdout"], language="text")


# ─────────────────────────── SPRINT 4 ──────────────────────────────────────
with tab4:
    st.subheader("Sprint 4 — Monitoring & Freshness")

    manifests = _all_manifests()
    if not manifests:
        st.info("Chưa có manifest nào. Chạy pipeline ở Sprint 1 trước.")
    else:
        # All runs overview
        st.markdown("**Tất cả pipeline runs**")
        rows = [{
            "run_id": m.get("run_id"),
            "timestamp": (m.get("run_timestamp") or "")[:19],
            "raw": m.get("raw_records"),
            "cleaned": m.get("cleaned_records"),
            "quarantine": m.get("quarantine_records"),
            "no_refund_fix": m.get("no_refund_fix", False),
            "skip_validate": m.get("skipped_validate", False),
        } for m in manifests]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # Freshness check
        st.divider()
        run_ids = [m.get("run_id", "") for m in manifests]
        sel_rid = st.selectbox("Chọn run để check freshness", run_ids, key="s4_sel")

        if st.button("▶  Check Freshness", key="s4_fresh_btn"):
            safe = (sel_rid or "").replace(":", "-")
            man_path = MAN_DIR / f"manifest_{safe}.json"
            sys.path.insert(0, str(LAB_DIR))
            from monitoring.freshness_check import check_manifest_freshness
            status, detail = check_manifest_freshness(man_path)
            st.session_state["s4_fresh"] = (status, detail)

        if "s4_fresh" in st.session_state:
            status, detail = st.session_state["s4_fresh"]
            _freshness_banner(status, detail)
            st.json(detail)

        # Manifest JSON viewer
        st.divider()
        sel_man = next((m for m in manifests if m.get("run_id") == sel_rid), None)
        if sel_man:
            with st.expander(f"Manifest JSON — {sel_rid}"):
                st.json(sel_man)
