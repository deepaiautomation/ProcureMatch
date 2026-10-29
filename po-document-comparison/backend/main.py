from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    import pdfplumber
except ImportError:  # Optional until a PDF is uploaded
    pdfplumber = None

APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("PO_DB_PATH", APP_DIR / "po_compare.db"))

app = FastAPI(title="PO Confirmation Comparison API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS purchase_orders (po_number TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS comparisons (comparison_id TEXT PRIMARY KEY, po_number TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS audit_events (event_id TEXT PRIMARY KEY, comparison_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL)")


def money(value: Any) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        raise ValueError(f"Invalid monetary value: {value}")


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def normalize_uom(value: Any) -> str:
    aliases = {"pcs": "EA", "piece": "EA", "pieces": "EA", "each": "EA", "kg": "KG", "kgs": "KG", "kilogram": "KG", "litre": "L", "liter": "L", "liters": "L", "ltrs": "L"}
    raw = normalize_text(value).upper()
    return aliases.get(raw.lower(), raw)


def parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def seed_data() -> None:
    with connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM purchase_orders").fetchone()[0]
        if count:
            return
        orders = [
            {
                "po_number": "4500010010", "supplier": "Apex Industrial Components", "company_code": "1000", "currency": "INR", "created_date": "2026-10-20",
                "items": [
                    {"item_no": "10", "material": "MAT-1001", "description": "Stainless steel fastener M10", "quantity": 1000, "uom": "EA", "unit_price": "500.00", "delivery_date": "2026-11-15", "plant": "HYD1"},
                    {"item_no": "20", "material": "MAT-1002", "description": "Industrial washer M10", "quantity": 500, "uom": "EA", "unit_price": "40.00", "delivery_date": "2026-11-15", "plant": "HYD1"}
                ], "payment_terms": "NET30", "incoterms": "DAP"
            },
            {
                "po_number": "4500010011", "supplier": "Vertex Packaging Pvt Ltd", "company_code": "1000", "currency": "INR", "created_date": "2026-10-21",
                "items": [
                    {"item_no": "10", "material": "PKG-2001", "description": "Corrugated carton 5-ply", "quantity": 2000, "uom": "EA", "unit_price": "28.50", "delivery_date": "2026-11-10", "plant": "HYD1"}
                ], "payment_terms": "NET45", "incoterms": "EXW"
            },
            {
                "po_number": "4500010012", "supplier": "Nova Electrical Systems", "company_code": "2000", "currency": "INR", "created_date": "2026-10-22",
                "items": [
                    {"item_no": "10", "material": "ELEC-3301", "description": "Three-phase contactor 32A", "quantity": 120, "uom": "EA", "unit_price": "1850.00", "delivery_date": "2026-11-18", "plant": "BLR1"},
                    {"item_no": "20", "material": "ELEC-3302", "description": "Thermal overload relay", "quantity": 120, "uom": "EA", "unit_price": "790.00", "delivery_date": "2026-11-18", "plant": "BLR1"}
                ], "payment_terms": "NET30", "incoterms": "FCA"
            }
        ]
        for po in orders:
            conn.execute("INSERT INTO purchase_orders VALUES (?, ?)", (po["po_number"], json.dumps(po)))


def get_po(po_number: str) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT payload FROM purchase_orders WHERE po_number=?", (po_number,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Purchase order {po_number} was not found")
    return json.loads(row["payload"])


def all_pos() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT payload FROM purchase_orders ORDER BY po_number DESC").fetchall()
    return [json.loads(r["payload"]) for r in rows]


def compare_confirmation(po: dict[str, Any], confirmation: dict[str, Any], filename: str = "synthetic-demo.pdf") -> dict[str, Any]:
    tolerances = {"quantity_pct": Decimal("0"), "price_pct": Decimal("0"), "delivery_days": 0}
    po_items = po.get("items", [])
    conf_items = confirmation.get("items", [])
    by_item: dict[str, list[dict[str, Any]]] = {}
    for item in conf_items:
        key = str(item.get("item_no", "")).lstrip("0") or "0"
        by_item.setdefault(key, []).append(item)

    rows: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []

    def add(field: str, item_no: str, expected: Any, actual: Any, severity: str = "medium", note: str = "") -> None:
        match = expected == actual
        rows.append({"field": field, "item_no": item_no or "HEADER", "expected": expected, "actual": actual, "status": "MATCH" if match else "MISMATCH", "severity": severity if not match else "none", "note": note})
        if not match:
            exceptions.append({"exception_id": str(uuid.uuid4()), "field": field, "item_no": item_no or "HEADER", "expected": expected, "actual": actual, "severity": severity, "status": "OPEN", "decision": None, "reason": None})

    add("PO number", "", normalize_text(po.get("po_number")), normalize_text(confirmation.get("po_number")), "high", "PO reference must identify the same order")
    add("Supplier", "", normalize_text(po.get("supplier")), normalize_text(confirmation.get("supplier")), "high", "Supplier identity differs")
    add("Currency", "", normalize_text(po.get("currency")), normalize_text(confirmation.get("currency")), "high", "Currency mismatch can change the commercial commitment")
    add("Payment terms", "", normalize_text(po.get("payment_terms")), normalize_text(confirmation.get("payment_terms")), "medium", "Check against negotiated payment terms")
    add("Incoterms", "", normalize_text(po.get("incoterms")), normalize_text(confirmation.get("incoterms")), "medium", "Check delivery responsibilities and named place")

    seen_conf_items: set[str] = set()
    for po_item in po_items:
        item_no = str(po_item.get("item_no", "")).lstrip("0") or "0"
        matches = by_item.get(item_no, [])
        if not matches:
            add("Item presence", item_no, "Present in confirmation", "Missing", "high", "PO item not confirmed by supplier")
            continue
        if len(matches) > 1:
            add("Duplicate item", item_no, "One confirmation line", f"{len(matches)} confirmation lines", "high", "Duplicate confirmation item requires review")
        conf_item = matches[0]
        seen_conf_items.add(item_no)
        add("Material", item_no, normalize_text(po_item.get("material")), normalize_text(conf_item.get("material")), "high", "Material code should match exactly")
        add("Unit of measure", item_no, normalize_uom(po_item.get("uom")), normalize_uom(conf_item.get("uom")), "high", "Units must be equivalent before quantity comparison")
        try:
            q_expected, q_actual = Decimal(str(po_item.get("quantity"))), Decimal(str(conf_item.get("quantity")))
            q_status = "MATCH" if q_expected == q_actual else "MISMATCH"
            add("Quantity", item_no, str(q_expected), str(q_actual), "high", "Quantity tolerance is 0% in the demo policy")
        except Exception:
            add("Quantity", item_no, po_item.get("quantity"), conf_item.get("quantity"), "high", "Quantity could not be parsed")
        try:
            p_expected, p_actual = money(po_item.get("unit_price")), money(conf_item.get("unit_price"))
            add("Unit price", item_no, str(p_expected), str(p_actual), "high", "Price tolerance is 0% in the demo policy")
        except ValueError:
            add("Unit price", item_no, po_item.get("unit_price"), conf_item.get("unit_price"), "high", "Price could not be parsed")
        d_expected, d_actual = parse_date(po_item.get("delivery_date")), parse_date(conf_item.get("delivery_date"))
        add("Delivery date", item_no, d_expected.isoformat() if d_expected else po_item.get("delivery_date"), d_actual.isoformat() if d_actual else conf_item.get("delivery_date"), "high", "Any date change is flagged for buyer review")
        if "description" in conf_item:
            # Description differences are informational and never substitute for material-code matching.
            if normalize_text(po_item.get("description")) != normalize_text(conf_item.get("description")):
                add("Description", item_no, po_item.get("description"), conf_item.get("description"), "low", "Description differs; validate against material/specification")

    for conf_item in conf_items:
        item_no = str(conf_item.get("item_no", "")).lstrip("0") or "0"
        if item_no not in {str(x.get("item_no", "")).lstrip("0") or "0" for x in po_items}:
            add("Unexpected item", item_no, "No extra item", conf_item.get("material", "Unknown material"), "high", "Supplier included a line not found in the PO")

    status = "MATCHED" if not exceptions else "REVIEW_REQUIRED"
    return {
        "comparison_id": str(uuid.uuid4()), "po_number": po["po_number"], "supplier": po.get("supplier"),
        "filename": filename, "created_at": now_iso(), "status": status, "rows": rows, "exceptions": exceptions,
        "summary": {"fields_checked": len(rows), "matched": sum(1 for r in rows if r["status"] == "MATCH"), "mismatches": len(exceptions), "open_exceptions": len(exceptions)},
        "confirmation": confirmation, "approval": {"status": "PENDING" if exceptions else "NOT_REQUIRED", "reviewer": None, "reviewed_at": None, "comment": None},
        "policy": {"quantity_tolerance_pct": str(tolerances["quantity_pct"]), "price_tolerance_pct": str(tolerances["price_pct"]), "delivery_date_tolerance_days": tolerances["delivery_days"]}
    }


def save_comparison(result: dict[str, Any]) -> dict[str, Any]:
    with connect() as conn:
        conn.execute("INSERT INTO comparisons VALUES (?, ?, ?, ?)", (result["comparison_id"], result["po_number"], json.dumps(result), result["created_at"]))
        conn.execute("INSERT INTO audit_events VALUES (?, ?, ?, ?)", (str(uuid.uuid4()), result["comparison_id"], json.dumps({"action": "COMPARISON_CREATED", "actor": "system", "details": {"filename": result["filename"]}}), result["created_at"]))
    return result


class DecisionRequest(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    reviewer: str = Field(min_length=2, max_length=120)
    comment: str = Field(min_length=3, max_length=1000)


class CompareRequest(BaseModel):
    po_number: str
    confirmation: dict[str, Any]
    filename: str = "manual-confirmation.json"


@app.on_event("startup")
def startup() -> None:
    init_db()
    seed_data()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "synthetic-demo", "timestamp": now_iso()}


@app.get("/api/purchase-orders")
def purchase_orders() -> list[dict[str, Any]]:
    return all_pos()


@app.get("/api/purchase-orders/{po_number}")
def purchase_order(po_number: str) -> dict[str, Any]:
    return get_po(po_number)


@app.get("/api/comparisons")
def comparisons() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT payload FROM comparisons ORDER BY created_at DESC").fetchall()
    return [json.loads(r["payload"]) for r in rows]


@app.get("/api/comparisons/{comparison_id}")
def comparison_detail(comparison_id: str) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT payload FROM comparisons WHERE comparison_id=?", (comparison_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Comparison not found")
    return json.loads(row["payload"])


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    items = comparisons()
    exceptions = [e for c in items for e in c["exceptions"]]
    return {
        "purchase_orders": len(all_pos()), "comparisons": len(items),
        "matched": sum(1 for c in items if c["status"] == "MATCHED"),
        "review_required": sum(1 for c in items if c["status"] == "REVIEW_REQUIRED"),
        "open_exceptions": sum(1 for e in exceptions if e["status"] == "OPEN"),
        "high_severity": sum(1 for e in exceptions if e["severity"] == "high" and e["status"] == "OPEN"),
        "recent": items[:5]
    }


@app.post("/api/compare")
def compare_json(payload: CompareRequest) -> dict[str, Any]:
    po = get_po(payload.po_number)
    if str(payload.confirmation.get("po_number", "")) != payload.po_number:
        # The comparison is still recorded so the PO-reference mismatch is visible to the buyer.
        pass
    return save_comparison(compare_confirmation(po, payload.confirmation, payload.filename))


def extract_pdf_text(data: bytes) -> str:
    if not pdfplumber:
        raise HTTPException(500, "PDF extraction dependency missing. Install requirements.txt")
    import io
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as exc:
        raise HTTPException(400, f"Could not read PDF: {exc}")


def parse_confirmation_text(text: str) -> dict[str, Any]:
    """Parser for the demo supplier-confirmation template; use Document Intelligence/OCR for varied layouts."""
    def field(pattern: str, label: str, required: bool = True) -> Optional[str]:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if not match and required:
            raise HTTPException(422, f"Could not extract required field '{label}'. Use the demo template or configure OCR extraction.")
        return match.group(1).strip() if match else None

    po_number = field(r"(?:PO\s*(?:Number|No\.?|#)|Purchase Order)\s*[:#-]?\s*([A-Z0-9-]+)", "PO number")
    supplier = field(r"Supplier\s*:\s*(.+)", "Supplier")
    currency = field(r"Currency\s*:\s*([A-Z]{3})", "Currency")
    payment_terms = field(r"Payment Terms\s*:\s*([A-Z0-9 -]+)", "Payment terms", False) or ""
    incoterms = field(r"Incoterms\s*:\s*([A-Z0-9]+)", "Incoterms", False) or ""
    items = []
    # Supported line format: Item: 10 | Material: MAT-1001 | Description: ... | Qty: 1000 | UOM: EA | Unit Price: 500.00 | Delivery Date: 2026-11-15
    for line in text.splitlines():
        if "Item:" not in line or "Material:" not in line:
            continue
        values = {}
        for key, pattern in {
            "item_no": r"Item:\s*([^|]+)", "material": r"Material:\s*([^|]+)", "description": r"Description:\s*([^|]+)",
            "quantity": r"Qty:\s*([0-9,.]+)", "uom": r"UOM:\s*([^|]+)", "unit_price": r"Unit Price:\s*([0-9,.]+)", "delivery_date": r"Delivery Date:\s*([^|]+)"
        }.items():
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                values[key] = m.group(1).strip()
        if "item_no" in values and "material" in values:
            try:
                values["quantity"] = float(values["quantity"].replace(",", ""))
                values["unit_price"] = values["unit_price"].replace(",", "")
            except (KeyError, ValueError):
                raise HTTPException(422, f"Could not parse quantity/price in line: {line}")
            items.append(values)
    if not items:
        raise HTTPException(422, "No line items found. PDF must use the documented demo template; scanned PDFs require OCR.")
    return {"po_number": po_number, "supplier": supplier, "currency": currency, "payment_terms": payment_terms, "incoterms": incoterms, "items": items}


@app.post("/api/upload-confirmation")
async def upload_confirmation(po_number: str = Form(...), file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(415, "Upload a PDF supplier confirmation")
    content = await file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(413, "PDF exceeds the 15 MB demo limit")
    text = extract_pdf_text(content)
    confirmation = parse_confirmation_text(text)
    po = get_po(po_number)
    return save_comparison(compare_confirmation(po, confirmation, file.filename))


@app.post("/api/comparisons/{comparison_id}/decision")
def decide(comparison_id: str, request: DecisionRequest) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT payload FROM comparisons WHERE comparison_id=?", (comparison_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Comparison not found")
        result = json.loads(row["payload"])
        if result["approval"]["status"] != "PENDING":
            raise HTTPException(409, "This comparison has already been reviewed")
        decision_status = "APPROVED" if request.decision == "APPROVE" else "REJECTED"
        result["approval"] = {"status": decision_status, "reviewer": request.reviewer, "reviewed_at": now_iso(), "comment": request.comment}
        for exception in result["exceptions"]:
            if exception["status"] == "OPEN":
                exception["status"] = decision_status
                exception["decision"] = request.decision
                exception["reason"] = request.comment
        result["status"] = "APPROVED_WITH_EXCEPTIONS" if request.decision == "APPROVE" else "REJECTED"
        conn.execute("UPDATE comparisons SET payload=? WHERE comparison_id=?", (json.dumps(result), comparison_id))
        event = {"action": "BUYER_" + request.decision, "actor": request.reviewer, "comment": request.comment}
        conn.execute("INSERT INTO audit_events VALUES (?, ?, ?, ?)", (str(uuid.uuid4()), comparison_id, json.dumps(event), now_iso()))
    return result


@app.get("/api/comparisons/{comparison_id}/audit")
def audit(comparison_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT payload, created_at FROM audit_events WHERE comparison_id=? ORDER BY created_at", (comparison_id,)).fetchall()
    return [{**json.loads(r["payload"]), "created_at": r["created_at"]} for r in rows]


@app.post("/api/demo/reset")
def reset_demo() -> dict[str, str]:
    with connect() as conn:
        conn.execute("DELETE FROM comparisons")
        conn.execute("DELETE FROM audit_events")
    return {"status": "reset", "message": "Comparison history cleared; purchase orders retained."}


@app.post("/api/demo/run-samples")
def run_samples() -> dict[str, Any]:
    # Clean deterministic demo run: one exact match, one with several differences, one with a missing line.
    with connect() as conn:
        conn.execute("DELETE FROM comparisons")
        conn.execute("DELETE FROM audit_events")
    pos = all_pos()
    confirmations = [
        {"po_number": "4500010010", "supplier": "Apex Industrial Components", "currency": "INR", "payment_terms": "NET30", "incoterms": "DAP", "items": [
            {"item_no": "10", "material": "MAT-1001", "description": "Stainless steel fastener M10", "quantity": 1000, "uom": "EA", "unit_price": "500.00", "delivery_date": "2026-11-15"},
            {"item_no": "20", "material": "MAT-1002", "description": "Industrial washer M10", "quantity": 500, "uom": "EA", "unit_price": "40.00", "delivery_date": "2026-11-15"}]},
        {"po_number": "4500010011", "supplier": "Vertex Packaging Pvt Ltd", "currency": "INR", "payment_terms": "NET45", "incoterms": "EXW", "items": [
            {"item_no": "10", "material": "PKG-2001", "description": "Corrugated carton 5-ply", "quantity": 1800, "uom": "EA", "unit_price": "30.00", "delivery_date": "2026-11-17"}]},
        {"po_number": "4500010012", "supplier": "Nova Electrical Systems", "currency": "INR", "payment_terms": "NET30", "incoterms": "FCA", "items": [
            {"item_no": "10", "material": "ELEC-3301", "description": "Three-phase contactor 32A", "quantity": 120, "uom": "EA", "unit_price": "1850.00", "delivery_date": "2026-11-18"}]}
    ]
    results = []
    by_number = {p["po_number"]: p for p in pos}
    for c in confirmations:
        result = save_comparison(compare_confirmation(by_number[c["po_number"]], c, f"supplier-confirmation-{c['po_number']}.pdf (sample)"))
        results.append(result)
    return {"created": len(results), "comparisons": results}
