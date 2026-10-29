# Backend

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

The API seeds three synthetic SAP-style purchase orders into `po_compare.db` on first startup. Run `POST /api/demo/run-samples` to create a clean demonstration set with one match and two exception cases.

## Demo PDF template

The current parser intentionally supports a small, predictable text-based PDF template. Each item must be on one line, for example:

```text
PO Number: 4500010010
Supplier: Apex Industrial Components
Currency: INR
Payment Terms: NET30
Incoterms: DAP
Item: 10 | Material: MAT-1001 | Description: Stainless steel fastener M10 | Qty: 1000 | UOM: EA | Unit Price: 500.00 | Delivery Date: 2026-11-15
```

For scanned PDFs or supplier-specific layouts, integrate Azure AI Document Intelligence or another OCR/document extraction service. Treat extracted values as untrusted until validated.

## Production hardening checklist

- Add SSO/OIDC, role-based authorization and company-code/plant data scope.
- Replace SQLite with PostgreSQL and use Alembic migrations.
- Add malware scanning, encrypted file storage, retention policy and file-size/page limits.
- Use a supplier-specific extraction schema and confidence thresholds; require human review for low confidence.
- Configure tolerances by purchasing organization, material group, currency and supplier contract.
- Add idempotency keys, duplicate-file/document detection and background processing for large batches.
- Connect to the approved SAP S/4HANA API/OData service with least-privilege credentials. Do not write PO changes automatically.
- Add tests, observability, rate limits, CSRF/security controls as appropriate, and an immutable audit strategy.
