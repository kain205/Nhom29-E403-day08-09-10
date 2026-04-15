# Runbook — Lab Day 10 (incident tối giản)

**Owner:** Nhóm 29 — E403  
**Cập nhật:** 2026-04-15

---

## Symptom

Agent hoặc user nhận được câu trả lời sai về policy, ví dụ:
- Trả lời "14 ngày làm việc" thay vì 7 ngày cho câu hỏi hoàn tiền.
- Trả lời "10 ngày phép năm" thay vì 12 ngày cho câu hỏi HR 2026.
- Retrieval trả về chunk từ bản policy cũ dù đã cập nhật.

---

## Detection

| Metric | Ngưỡng cảnh báo | Công cụ |
|--------|----------------|---------|
| `hits_forbidden=yes` trong eval CSV | Bất kỳ dòng nào | `python eval_retrieval.py` |
| `expectation[refund_no_stale_14d_window] FAIL` | Xuất hiện trong log | `artifacts/logs/run_*.log` |
| `expectation[hr_leave_no_stale_10d_annual] FAIL` | Xuất hiện trong log | `artifacts/logs/run_*.log` |
| `freshness_check=FAIL` | `age_hours > sla_hours` | manifest + log |
| `quarantine_records` tăng đột biến | > 30% raw_records | manifest JSON |

---

## Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|-----------------|
| 1 | Mở `artifacts/manifests/manifest_<run-id>.json` — kiểm tra `no_refund_fix`, `skipped_validate`, `latest_exported_at` | `no_refund_fix=false`, `skipped_validate=false`; `latest_exported_at` không quá cũ |
| 2 | Mở `artifacts/quarantine/quarantine_<run-id>.csv` — lọc cột `reason` | Không có row nào bị quarantine sai; nếu có `reason=stale_hr_policy_effective_date` thì bản HR cũ đã bị chặn đúng |
| 3 | Chạy `python eval_retrieval.py --out artifacts/eval/debug_eval.csv` | `hits_forbidden=no` cho tất cả câu; `contains_expected=yes` |
| 4 | Kiểm tra log: `grep "FAIL" artifacts/logs/run_<run-id>.log` | Không có dòng `expectation[...] FAIL` với severity halt |
| 5 | Kiểm tra collection: rerun `python etl_pipeline.py run --run-id debug` | Log có `embed_prune_removed=N` nếu có vector cũ bị xóa |

---

## Mitigation

1. **Rerun pipeline chuẩn** (không flag inject):
   ```bash
   python etl_pipeline.py run --run-id fix-$(date +%Y%m%d)
   ```
2. **Kiểm tra lại eval** sau rerun:
   ```bash
   python eval_retrieval.py --out artifacts/eval/after_fix.csv
   ```
3. Nếu vẫn fail: kiểm tra `data/raw/policy_export_dirty.csv` — có thể nguồn raw đã bị ghi đè bởi bản stale.
4. **Rollback embed tạm thời**: xóa `chroma_db/` và rerun từ đầu (collection sẽ được tạo lại từ cleaned CSV).

---

## Prevention

- Thêm expectation mới khi phát hiện failure mode mới (ví dụ E7, E8 được thêm sau Sprint 2).
- Đặt `FRESHNESS_SLA_HOURS` trong `.env` phù hợp với chu kỳ export thực tế.
- Không commit file `policy_export_dirty.csv` đã bị sửa tay — luôn rerun pipeline từ nguồn gốc.
- Đồng bộ `ALLOWED_DOC_IDS` trong `cleaning_rules.py` với `allowed_doc_ids` trong `contracts/data_contract.yaml` khi thêm tài liệu mới.

---

## Giải thích PASS / WARN / FAIL freshness

`freshness_check` đọc trường `latest_exported_at` trong manifest (= max `exported_at` của cleaned rows) và so sánh với `FRESHNESS_SLA_HOURS` (mặc định 24h):

| Trạng thái | Điều kiện | Ý nghĩa |
|-----------|-----------|---------|
| `PASS` | `age_hours ≤ sla_hours` | Data đủ mới, pipeline đã chạy trong SLA |
| `FAIL` | `age_hours > sla_hours` | Data cũ hơn SLA — cần rerun hoặc xem xét lại SLA |
| `WARN` | Không có timestamp trong manifest | Manifest thiếu `latest_exported_at` — kiểm tra R9 |

**Trong lab này:** `freshness_check=FAIL` với `age_hours≈120h` là **bình thường và có chủ đích** — CSV mẫu có `exported_at=2026-04-10T08:00:00` (5 ngày trước ngày chạy lab). SLA 24h áp cho pipeline production; với data snapshot tĩnh trong lab, FAIL không ảnh hưởng tính đúng đắn của pipeline.
