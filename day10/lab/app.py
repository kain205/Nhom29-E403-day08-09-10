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

def _run_pipeline(run_id: str, *, no_refund_fix=False, skip_validate=False):
    cmd = [sys.executable, "etl_pipeline.py", "run", "--run-id", run_id]
    if no_refund_fix:
        cmd.append("--no-refund-fix")
    if skip_validate:
        cmd.append("--skip-validate")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(LAB_DIR))
    return r.stdout + ("\n" + r.stderr if r.stderr.strip() else ""), r.returncode


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

        # Three-column table: Raw | Cleaned | Quarantine
        safe = rid_used.replace(":", "-")
        c_raw, c_clean, c_quar = st.columns(3)

        with c_raw:
            st.markdown(f"**Raw CSV — {man.get('raw_records', '?')} records**")
            df = _load_csv(RAW_CSV)
            if df is not None:
                st.dataframe(df, use_container_width=True, height=300, hide_index=True)

        with c_clean:
            st.markdown(f"**Cleaned — {man.get('cleaned_records', '?')} records**")
            df = _load_csv(CLEAN_DIR / f"cleaned_{safe}.csv")
            if df is not None:
                st.dataframe(df, use_container_width=True, height=300, hide_index=True)

        with c_quar:
            st.markdown(f"**Quarantine — {man.get('quarantine_records', '?')} records**")
            df = _load_csv(QUAR_DIR / f"quarantine_{safe}.csv")
            if df is not None:
                show_cols = [c for c in ["chunk_id", "doc_id", "chunk_text", "reason"]
                             if c in df.columns]
                st.dataframe(df[show_cols] if show_cols else df,
                             use_container_width=True, height=300, hide_index=True)

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
    st.warning(
        "Inject sẽ **ghi đè vector store**. "
        "Sau khi demo nhớ nhấn **Restore** để đưa DB về trạng thái clean.",
        icon="⚠️",
    )

    c_left, c_right = st.columns(2)

    # ---- Clean side ----
    with c_left:
        st.markdown("### Clean pipeline")
        st.caption("refund fix ON · validate ON")
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
            df_eval = _load_csv(st.session_state.get("s3_clean_eval"))
            if df_eval is not None:
                st.markdown("**Eval — retrieval results**")
                show = [c for c in ["question_id", "contains_expected",
                                    "hits_forbidden", "top1_doc_id"] if c in df_eval.columns]
                st.dataframe(df_eval[show], use_container_width=True, hide_index=True)

    # ---- Inject side ----
    with c_right:
        st.markdown("### Inject (bad data)")
        st.caption("--no-refund-fix  --skip-validate")
        if st.button("▶  Run Inject + Eval", key="s3_inject_btn", type="secondary"):
            with st.spinner("Pipeline inject…"):
                stdout_i, rc_i = _run_pipeline("s3-inject",
                                               no_refund_fix=True, skip_validate=True)
            with st.spinner("Eval retrieval…"):
                _, _, eval_path_i = _run_eval("s3_inject_eval.csv")
            st.session_state.update(
                s3_inject_stdout=stdout_i, s3_inject_rc=rc_i,
                s3_inject_eval=eval_path_i,
            )

        if "s3_inject_stdout" in st.session_state:
            si = st.session_state["s3_inject_stdout"]
            if "PIPELINE_OK" in si:
                st.success("Pipeline ran (validate skipped)")
            elif "PIPELINE_HALT" in si:
                st.error("PIPELINE_HALT")
            man = _load_manifest("s3-inject")
            if man:
                cc1, cc2 = st.columns(2)
                cc1.metric("Cleaned", man.get("cleaned_records"))
                cc2.metric("Quarantine", man.get("quarantine_records"))
            df_eval = _load_csv(st.session_state.get("s3_inject_eval"))
            if df_eval is not None:
                st.markdown("**Eval — retrieval results**")
                show = [c for c in ["question_id", "contains_expected",
                                    "hits_forbidden", "top1_doc_id"] if c in df_eval.columns]
                st.dataframe(df_eval[show], use_container_width=True, hide_index=True)

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

        # Restore button
        st.divider()
        if st.button("↺  Restore DB về trạng thái clean", key="s3_restore_btn"):
            with st.spinner("Restoring…"):
                stdout_r, rc_r = _run_pipeline("s3-restore")
            if "PIPELINE_OK" in stdout_r:
                st.success("DB đã restore về clean.")
            else:
                st.error("Restore failed — xem log bên dưới.")
            with st.expander("Restore log"):
                st.code(stdout_r, language="text")

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
