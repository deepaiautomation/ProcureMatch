# ProcureMatch — Purchase-Order Document Comparison

A full-stack demo that compares synthetic SAP-style purchase orders with supplier confirmation PDFs, flags discrepancies deterministically, and records human approval decisions.

## Features

- React + JavaScript JSX procurement control-tower UI
- FastAPI REST backend and SQLite persistence
- Synthetic SAP-style POs with multiple line items
- Demo run creates a clean match and exception scenarios
- PDF upload and text extraction for a documented demo confirmation template
- Header and line-item checks: PO number, supplier, currency, payment terms, Incoterms, material, UOM, quantity, price, delivery date, missing/extra/duplicate lines
- Exception severity, buyer approve/reject, comments, and audit trail
- Swagger API docs at `/docs`

## Run the app

Requirements: Python 3.10+ and Node.js 18+.

### 1. Start the backend

```bash
cd backend
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 2. Start the frontend in a second terminal

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Use **Run demo data** to load sample comparisons. The UI defaults to the backend at `http://localhost:8000`; set `VITE_API_URL` in a `.env` file if needed.

### 3. PDF format supported by the prototype

The parser currently expects text-based PDFs with fields similar to the following. Each item is on one line:

```text
PO Number: 4500010010
Supplier: Apex Industrial Components
Currency: INR
Payment Terms: NET30
Incoterms: DAP
Item: 10 | Material: MAT-1001 | Description: Stainless steel fastener M10 | Qty: 1000 | UOM: EA | Unit Price: 500.00 | Delivery Date: 2026-11-15
Item: 20 | Material: MAT-1002 | Description: Industrial washer M10 | Qty: 500 | UOM: EA | Unit Price: 40.00 | Delivery Date: 2026-11-15
```

Real supplier confirmations vary significantly. For production, use Azure AI Document Intelligence (or another approved OCR/document extraction service), supplier-specific extraction schemas, field confidence thresholds, and human review for uncertain extraction. The current OCR support is not enabled for scanned image-only PDFs.

## API endpoints

- `GET /api/health`
- `GET /api/dashboard`
- `GET /api/purchase-orders`
- `GET /api/comparisons`
- `GET /api/comparisons/{comparison_id}`
- `GET /api/comparisons/{comparison_id}/audit`
- `POST /api/upload-confirmation` (multipart: `po_number`, `file`)
- `POST /api/compare` (JSON confirmation payload)
- `POST /api/comparisons/{comparison_id}/decision` (APPROVE/REJECT, reviewer, comment)
- `POST /api/demo/run-samples`
- `POST /api/demo/reset`

## Comparison rules

- Numeric fields are parsed as `Decimal` where applicable.
- Material, supplier, currency, PO number, payment terms and Incoterms are normalized for whitespace/case; material IDs otherwise require exact match.
- UOM aliases such as `pieces` and `pcs` normalize to `EA`.
- Demo policy is intentionally strict: zero quantity/price tolerance and any delivery-date change is flagged. Configure tolerance by purchasing organization, supplier, material group and contract before production use.
- Extra, missing and duplicate items are exceptions. A changed description is a low-severity informational mismatch; it never overrides material-code validation.
- An approval records reviewer, timestamp and comment. It does not modify SAP data.

## Important production gaps

This is a working starter, not a production-certified procurement system. Before using real data, add SSO/OIDC and authorization, company-code/plant scope enforcement, PostgreSQL migrations, secure file storage, malware scanning, retention controls, background jobs, idempotency/duplicate detection, robust OCR and extraction confidence handling, SAP API integration, observability, tests and a tamper-resistant audit log. Approval semantics should be aligned with your procurement policy; `Approve with exceptions` means the reviewer accepts the confirmation despite flagged differences.
