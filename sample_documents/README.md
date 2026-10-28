# AICTE FDR Portal — Sample Documents

This folder contains realistic, officially formatted Fixed Deposit Receipts (FDRs) and Bank Lien Confirmation documents generated for testing the **AICTE FDR Management Portal**.

All PDFs contain standard vector text layers compatible with the portal's automatic extraction engine (`pypdf` + regex extraction in `app.extract`).

---

## Sample Documents Catalog

| # | File Name | Bank Name | FDR Reference No | Principal Amount | Issue Date | Maturity Date | Test Scenario & Purpose |
|---|---|---|---|---|---|---|---|
| **1** | [`1_SBI_FDR_35Lakhs_Fresh_Valid.pdf`](./1_SBI_FDR_35Lakhs_Fresh_Valid.pdf) | State Bank of India | `FDR/SBI/2026/884920` | ₹35,00,000.00 | 15/07/2024 | 15/07/2029 | **Standard Fresh Deposit**: 5-Year Technical Institution deposit under joint lien with Regional Officer AICTE WRO. |
| **2** | [`2_PNB_FDR_15Lakhs_Renewal.pdf`](./2_PNB_FDR_15Lakhs_Renewal.pdf) | Punjab National Bank | `FDR/PNB/2026/301984` | ₹15,00,000.00 | 10/01/2026 | 10/01/2031 | **Renewal Deposit**: Renewal receipt linking to prior deposit `FDR/PNB/2021/110294` for FDR Lineage & Trace. |
| **3** | [`3_BOB_FDR_25Lakhs_Discrepancy_ShortTenure.pdf`](./3_BOB_FDR_25Lakhs_Discrepancy_ShortTenure.pdf) | Bank of Baroda | `FDR/BOB/2025/551203` | ₹25,00,000.00 | 01/03/2025 | 01/03/2028 | **Discrepancy & Scrutiny Test**: Non-compliant 3-year tenure (violates 5-year requirement) & solo account title to test rejection/deficiency flags. |
| **4** | [`4_HDFC_FDR_50Lakhs_PG_Program_8Years.pdf`](./4_HDFC_FDR_50Lakhs_PG_Program_8Years.pdf) | HDFC Bank Ltd | `FDR/HDFC/2026/772109` | ₹50,00,000.00 | 20/05/2025 | 20/05/2033 | **8-Year PG Program Deposit**: Long-term technical program security deposit under AICTE Approval Process Handbook. |
| **5** | [`5_CANARA_FDR_10Lakhs_Expiring_Soon.pdf`](./5_CANARA_FDR_10Lakhs_Expiring_Soon.pdf) | Canara Bank | `FDR/CAN/2021/660421` | ₹10,00,000.00 | 01/11/2021 | 15/11/2026 | **Expiring Soon Trigger**: Deposit maturing in less than 30 days to test automatic status transitions (`EXPIRING`), calendar alerts, and renewal notifications. |
| **6** | [`6_Bank_Lien_Confirmation_Letter.pdf`](./6_Bank_Lien_Confirmation_Letter.pdf) | State Bank of India | `FDR/SBI/2026/884920` | ₹35,00,000.00 | 15/07/2024 | 15/07/2029 | **Bank Lien Certificate**: Official branch certificate stating lien noted in Core Banking System (CBS) in favour of AICTE. |

---

## How to Test in the Portal

### Option A: Via the Web UI
1. Log in to `http://localhost:3000/login` as an institution user (`institution1` / `Institute@12345`) or admin (`admin` / `Admin@12345`).
2. Navigate to **New FDR** (`/deposits/new`).
3. Drag and drop any of the PDF files above into the upload box.
4. Watch the portal's automatic extraction engine parse the document and populate:
   - FDR Reference Number
   - Bank Name
   - Amount
   - Issue Date
   - Maturity Date
5. Review the extracted fields and click **Create FDR**.

### Option B: Via the API
```bash
TOKEN=$(curl -s -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin@12345"}' | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

curl -X POST http://localhost:8001/api/extract/fdr \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@sample_documents/1_SBI_FDR_35Lakhs_Fresh_Valid.pdf"
```

### Option C: Re-generate Samples
To regenerate these files at any time:
```bash
cd backend
.venv/bin/python scripts/generate_sample_fdrs.py
```
