# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** ___________  
**Thành viên:**
| Tên | Vai trò (Day 10) | Email |
|-----|------------------|-------|
| ___ | Ingestion / Raw Owner | ___ |
| ___ | Cleaning & Quality Owner | ___ |
| ___ | Embed & Idempotency Owner | ___ |
| ___ | Monitoring / Docs Owner | ___ |

**Ngày nộp:** ___________  
**Repo:** ___________  
**Độ dài khuyến nghị:** 600–1000 từ

---

> **Nộp tại:** `reports/group_report.md`  
> **Deadline commit:** xem `SCORING.md` (code/trace sớm; report có thể muộn hơn nếu được phép).  
> Phải có **run_id**, **đường dẫn artifact**, và **bằng chứng before/after** (CSV eval hoặc screenshot).

---

## 1. Pipeline tổng quan (150–200 từ)

> Nguồn raw là gì (CSV mẫu / export thật)? Chuỗi lệnh chạy end-to-end? `run_id` lấy ở đâu trong log?

**Tóm tắt luồng:**

Nguồn raw: `data/raw/policy_export_dirty.csv` (10 records, CSV mẫu có duplicate, thiếu ngày, doc_id lạ, xung đột version HR, chunk policy sai cửa sổ hoàn tiền).  
Luồng: ingest raw → cleaning rules → expectation suite → embed Chroma (upsert + prune) → manifest + freshness check.  
`run_id` xuất hiện ở dòng đầu log và được ghi vào `artifacts/manifests/manifest_<run-id>.json`.

**Kết quả Sprint 2 (run_id=sprint2, 2026-04-15):**

| Metric | Giá trị |
|--------|---------|
| raw_records | 10 |
| cleaned_records | 6 |
| quarantine_records | 4 |
| embed_upsert count | 6 |
| expectations passed | 8/8 (E1–E8) |
| freshness_check | FAIL (age=120.6h, SLA=24h — data snapshot cũ, expected) |
| manifest | `artifacts/manifests/manifest_sprint2.json` |

**Lệnh chạy một dòng (copy từ README thực tế của nhóm):**

```bash
python etl_pipeline.py run
```

---

## 2. Cleaning & expectation (150–200 từ)

> Baseline đã có nhiều rule (allowlist, ngày ISO, HR stale, refund, dedupe…). Nhóm thêm **≥3 rule mới** + **≥2 expectation mới**. Khai báo expectation nào **halt**.

### 2a. Bảng metric_impact (bắt buộc — chống trivial)

| Rule / Expectation mới (tên ngắn) | Loại | Severity | Trước inject | Sau inject | Chứng cứ |
|-----------------------------------|------|----------|--------------|------------|-----------|
| R7: `strip_cleaning_annotation` | cleaning rule | — | chunk_text chứa `[cleaned: stale_refund_window]` trong raw → chunk_id thay đổi sau strip | chunk_text sạch, chunk_id mới, vector cũ bị prune | `artifacts/cleaned/cleaned_sprint2.csv` — cột chunk_text không còn tag |
| R8: `quarantine_future_effective_date` | cleaning rule | — | inject row `effective_date=2099-01-01` → quarantine_records tăng từ 4 → 5 | quarantine_records=5, chunk không vào index | `artifacts/quarantine/quarantine_sprint2_inject.csv` reason=`future_effective_date` |
| R9: `quarantine_invalid_exported_at` | cleaning rule | — | inject row với `exported_at=""` → quarantine_records tăng từ 4 → 5; manifest.latest_exported_at không bị sai | quarantine_records=5 | `artifacts/quarantine/quarantine_sprint2_inject.csv` reason=`invalid_exported_at` |
| E7: `no_future_effective_date` | expectation | **halt** | inject future-dated row + skip R8 → E7 FAIL → pipeline halt | sau R8 fix: E7 OK | log sprint2: `expectation[no_future_effective_date] OK` |
| E8: `no_invalid_exported_at` | expectation | warn | inject row `exported_at=""` + skip R9 → E8 FAIL (warn, không halt) | sau R9 fix: E8 OK | log sprint2: `expectation[no_invalid_exported_at] OK` |

**Rule chính (baseline + mở rộng):**

- R1: Quarantine `doc_id` không thuộc allowlist → row 9 (`legacy_catalog_xyz_zzz`) bị quarantine
- R2: Chuẩn hoá `effective_date` DD/MM/YYYY → ISO; row 10 (`01/02/2026`) được parse thành `2026-02-01`
- R3: Quarantine HR stale (`effective_date < 2026-01-01`) → row 7 bị quarantine
- R4: Quarantine `chunk_text` rỗng → row 5 bị quarantine
- R5: Dedupe `chunk_text` → row 2 (trùng row 1) bị quarantine
- R6: Fix refund 14→7 ngày → row 3 được sửa + tag `[cleaned: stale_refund_window]`
- **R7 (mới)**: Strip tag `[cleaned: ...]` lọt vào raw từ lần chạy trước → chunk_text sạch
- **R8 (mới)**: Quarantine `effective_date > today` → chặn policy chưa phát hành
- **R9 (mới)**: Quarantine chunk có `exported_at` rỗng hoặc sai format → manifest `latest_exported_at` không bị nhiễm bởi timestamp rác

**Ví dụ 1 lần expectation fail và cách xử lý:**

Khi chạy `--no-refund-fix --skip-validate` (Sprint 3 inject), expectation E3 `refund_no_stale_14d_window` FAIL vì chunk vẫn chứa "14 ngày làm việc". Pipeline in `PIPELINE_HALT` nhưng do `--skip-validate` nên tiếp tục embed — đây là hành vi có chủ đích để tạo bằng chứng before/after.

---

## 3. Before / after ảnh hưởng retrieval hoặc agent (200–250 từ)

> Bắt buộc: inject corruption (Sprint 3) — mô tả + dẫn `artifacts/eval/…` hoặc log.

**Kịch bản inject:**

_________________

**Kết quả định lượng (từ CSV / bảng):**

_________________

---

## 4. Freshness & monitoring (100–150 từ)

> SLA bạn chọn, ý nghĩa PASS/WARN/FAIL trên manifest mẫu.

_________________

---

## 5. Liên hệ Day 09 (50–100 từ)

> Dữ liệu sau embed có phục vụ lại multi-agent Day 09 không? Nếu có, mô tả tích hợp; nếu không, giải thích vì sao tách collection.

_________________

---

## 6. Rủi ro còn lại & việc chưa làm

- …
