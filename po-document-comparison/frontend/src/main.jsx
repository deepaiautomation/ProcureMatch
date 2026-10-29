import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Activity, AlertTriangle, ArrowDownToLine, ArrowRight, BadgeCheck, Check, CheckCircle2, ChevronDown, CircleHelp, Clock3, FileCheck2, FileText, Filter, GitCompareArrows, Layers3, LayoutDashboard, PackageSearch, RefreshCw, Search, ShieldCheck, UploadCloud, X, XCircle } from 'lucide-react'
import './styles.css'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const fmt = n => new Intl.NumberFormat('en-IN').format(n || 0)
const currency = (v, c = 'INR') => { try { return new Intl.NumberFormat('en-IN', { style: 'currency', currency: c, maximumFractionDigits: 2 }).format(Number(v)) } catch { return v ?? '—' } }
const shortDate = value => value ? new Date(value).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, options)
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`)
  return data
}

function Status({ value }) {
  const map = {
    MATCHED: ['good', 'Matched'], REVIEW_REQUIRED: ['warn', 'Review required'], PENDING: ['warn', 'Pending review'],
    APPROVED: ['good', 'Approved'], APPROVED_WITH_EXCEPTIONS: ['good', 'Approved with exceptions'], REJECTED: ['bad', 'Rejected'],
    OPEN: ['warn', 'Open'], MATCH: ['good', 'Match'], MISMATCH: ['bad', 'Mismatch'], APPROVEDD: ['good', 'Approved'], REJECTEDD: ['bad', 'Rejected'], NOT_REQUIRED: ['neutral', 'No review needed']
  }
  const [kind, label] = map[value] || ['neutral', value || 'Unknown']
  return <span className={`status ${kind}`}><span className="status-dot" />{label}</span>
}

function Metric({ label, value, note, icon: Icon, tone = 'blue' }) {
  return <div className="metric-card"><div className={`metric-icon ${tone}`}><Icon size={19}/></div><div className="metric-label">{label}</div><div className="metric-value">{value}</div><div className="metric-note">{note}</div></div>
}

function App() {
  const [dashboard, setDashboard] = useState(null)
  const [orders, setOrders] = useState([])
  const [comparisons, setComparisons] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [filter, setFilter] = useState('ALL')
  const [search, setSearch] = useState('')
  const [poNumber, setPoNumber] = useState('')
  const [file, setFile] = useState(null)
  const [reviewer, setReviewer] = useState('Procurement Buyer')
  const [comment, setComment] = useState('Reviewed against supplier terms.')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [uploadOpen, setUploadOpen] = useState(false)

  const refresh = useCallback(async (keepSelection = true) => {
    try {
      const [d, p, c] = await Promise.all([api('/api/dashboard'), api('/api/purchase-orders'), api('/api/comparisons')])
      setDashboard(d); setOrders(p); setComparisons(c)
      if (!poNumber && p.length) setPoNumber(p[0].po_number)
      if (keepSelection && selectedId && !c.some(x => x.comparison_id === selectedId)) setSelectedId(null)
    } catch (e) { setError(`${e.message}. Is the FastAPI backend running on ${API}?`) }
  }, [selectedId, poNumber])

  useEffect(() => { refresh() }, [])
  const selected = comparisons.find(c => c.comparison_id === selectedId) || comparisons[0] || null
  const filtered = useMemo(() => comparisons.filter(c => {
    const matchesStatus = filter === 'ALL' || (filter === 'EXCEPTIONS' ? c.status === 'REVIEW_REQUIRED' : filter === 'PENDING' ? c.approval?.status === 'PENDING' : c.status === filter)
    const q = search.trim().toLowerCase()
    return matchesStatus && (!q || `${c.po_number} ${c.supplier} ${c.filename}`.toLowerCase().includes(q))
  }), [comparisons, filter, search])
  const activeExceptions = selected?.exceptions || []
  const openExceptions = activeExceptions.filter(e => e.status === 'OPEN')

  async function runSamples() {
    setBusy(true); setError(''); setNotice('')
    try { const result = await api('/api/demo/run-samples', { method: 'POST' }); await refresh(false); if (result.comparisons?.length) setSelectedId(result.comparisons[1]?.comparison_id || result.comparisons[0].comparison_id); setNotice('Demo comparisons generated: one clean match and two exception cases.') }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  async function uploadPdf(e) {
    e.preventDefault(); if (!file || !poNumber) return
    setBusy(true); setError(''); setNotice('')
    try {
      const body = new FormData(); body.append('po_number', poNumber); body.append('file', file)
      const result = await api('/api/upload-confirmation', { method: 'POST', body })
      await refresh(false); setSelectedId(result.comparison_id); setNotice(`Compared ${file.name} against PO ${poNumber}.`); setFile(null); setUploadOpen(false)
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  async function decide(decision) {
    if (!selected) return
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await api(`/api/comparisons/${selected.comparison_id}/decision`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision, reviewer, comment }) })
      await refresh(false); setSelectedId(result.comparison_id); setNotice(`Comparison ${decision.toLowerCase()}d and audit event recorded.`)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><GitCompareArrows size={21}/></div><div><div className="brand-name">ProcureMatch</div><div className="brand-caption">SUPPLIER INTELLIGENCE</div></div></div>
      <div className="workspace-label">WORKSPACE</div>
      <button className="nav-item active"><LayoutDashboard size={18}/> Overview <span className="nav-pill">Live</span></button>
      <button className="nav-item" onClick={() => setUploadOpen(true)}><UploadCloud size={18}/> Document intake</button>
      <button className="nav-item" onClick={() => { setFilter('EXCEPTIONS'); document.getElementById('comparison-list')?.scrollIntoView({ behavior: 'smooth' }) }}><AlertTriangle size={18}/> Exceptions <span className="nav-count">{dashboard?.open_exceptions ?? '—'}</span></button>
      <button className="nav-item" onClick={() => { setFilter('PENDING'); document.getElementById('comparison-list')?.scrollIntoView({ behavior: 'smooth' }) }}><ShieldCheck size={18}/> Buyer approvals</button>
      <div className="sidebar-bottom"><div className="connection-card"><div className="connection-top"><span className="connection-dot"/> Demo environment</div><p>Synthetic SAP-style PO data. No live ERP changes are made.</p><button onClick={() => refresh()}><RefreshCw size={13}/> Refresh data</button></div><div className="profile"><div className="avatar">DA</div><div className="profile-copy"><strong>DeepAI Automation</strong><span>Procurement workspace</span></div><ChevronDown size={15}/></div></div>
    </aside>

    <main className="main-content">
      <header className="topbar"><div className="breadcrumb">Procurement <span>/</span> <strong>PO confirmation review</strong></div><div className="top-actions"><span className="env-chip"><span className="connection-dot"/> Sandbox</span><button className="icon-button" title="Refresh" onClick={() => refresh()}><RefreshCw size={17}/></button><div className="avatar small">DA</div></div></header>
      <div className="page-wrap">
        <div className="page-heading"><div><div className="eyebrow">PROCUREMENT CONTROL TOWER</div><h1>Purchase order comparison</h1><p>Validate supplier confirmations against SAP purchase orders before commitments are accepted.</p></div><div className="heading-actions"><button className="button secondary" onClick={runSamples} disabled={busy}><Activity size={16}/>{busy ? 'Working…' : 'Run demo data'}</button><button className="button primary" onClick={() => setUploadOpen(true)}><UploadCloud size={16}/> Upload confirmation</button></div></div>
        {error && <div className="alert error"><AlertTriangle size={17}/><span>{error}</span><button onClick={() => setError('')}><X size={16}/></button></div>}
        {notice && <div className="alert success"><CheckCircle2 size={17}/><span>{notice}</span><button onClick={() => setNotice('')}><X size={16}/></button></div>}
        <div className="metric-grid">
          <Metric label="Purchase orders" value={fmt(dashboard?.purchase_orders)} note="Available for comparison" icon={Layers3} tone="blue"/>
          <Metric label="Documents compared" value={fmt(dashboard?.comparisons)} note="All processed confirmations" icon={FileCheck2} tone="violet"/>
          <Metric label="Need buyer review" value={fmt(dashboard?.review_required)} note="At least one discrepancy" icon={AlertTriangle} tone="amber"/>
          <Metric label="Open exceptions" value={fmt(dashboard?.open_exceptions)} note={`${fmt(dashboard?.high_severity)} high severity`} icon={Clock3} tone="rose"/>
        </div>

        <div className="section-head"><div><h2>Comparison workspace</h2><p>Choose a comparison to inspect line-level differences and take action.</p></div><div className="section-meta"><span className="tiny-dot"/> Rules engine active</div></div>
        <div className="workspace-grid">
          <section className="panel list-panel" id="comparison-list">
            <div className="panel-head"><div><h3>Recent comparisons</h3><span className="subtle">{filtered.length} records</span></div><button className="icon-button light" title="Filter"><Filter size={16}/></button></div>
            <div className="list-tools"><div className="search-box"><Search size={15}/><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search PO, supplier…"/></div><select value={filter} onChange={e => setFilter(e.target.value)} aria-label="Filter comparisons"><option value="ALL">All statuses</option><option value="EXCEPTIONS">Review required</option><option value="PENDING">Pending approval</option><option value="MATCHED">Matched</option><option value="REJECTED">Rejected</option></select></div>
            <div className="comparison-list">
              {filtered.length === 0 ? <div className="empty-state"><PackageSearch size={28}/><strong>No comparisons yet</strong><p>Run the demo data or upload a supplier PDF to get started.</p><button className="button primary compact" onClick={runSamples}>Run demo</button></div> : filtered.map(c => <button key={c.comparison_id} className={`comparison-row ${selected?.comparison_id === c.comparison_id ? 'selected' : ''}`} onClick={() => setSelectedId(c.comparison_id)}><div className="row-icon"><FileText size={18}/></div><div className="row-main"><div className="row-title"><strong>PO {c.po_number}</strong><span className="row-date">{shortDate(c.created_at)}</span></div><div className="row-supplier">{c.supplier}</div><div className="row-bottom"><Status value={c.status}/><span className="exception-count">{c.summary?.mismatches ?? 0} discrepancies</span></div></div><ArrowRight size={15} className="row-arrow"/></button>)}
            </div>
            <div className="list-footer"><span><span className="tiny-dot"/> Data saved locally</span><span>Auto-refresh on action</span></div>
          </section>

          <section className="panel detail-panel">
            {selected ? <>
              <div className="detail-top"><div><div className="detail-kicker">COMPARISON DETAIL</div><h3>PO {selected.po_number}</h3><p>{selected.supplier}</p></div><Status value={selected.status}/></div>
              <div className="document-strip"><div className="doc-mini"><div className="doc-icon"><FileText size={18}/></div><div><strong>SAP purchase order</strong><span>PO {selected.po_number}</span></div><BadgeCheck size={17} className="doc-check"/></div><div className="versus">VS</div><div className="doc-mini"><div className="doc-icon pdf"><FileText size={18}/></div><div><strong>Supplier confirmation</strong><span className="filename" title={selected.filename}>{selected.filename}</span></div><span className="pdf-label">PDF</span></div></div>
              <div className="detail-metrics"><div><span>Fields checked</span><strong>{selected.summary?.fields_checked ?? 0}</strong></div><div><span>Matched</span><strong className="green-text">{selected.summary?.matched ?? 0}</strong></div><div><span>Discrepancies</span><strong className="red-text">{selected.summary?.mismatches ?? 0}</strong></div></div>
              <div className="table-head"><div><h4>Field-level validation</h4><span className="subtle">Exact comparison · configured tolerances</span></div><span className="rule-tag"><ShieldCheck size={13}/> Deterministic rules</span></div>
              <div className="table-wrap"><table><thead><tr><th>Field / item</th><th>PO value</th><th>Supplier value</th><th>Result</th></tr></thead><tbody>{selected.rows.map((r, i) => <tr key={`${r.field}-${r.item_no}-${i}`} className={r.status === 'MISMATCH' ? 'mismatch-row' : ''}><td><div className="field-name">{r.field}</div><div className="field-sub">{r.item_no === 'HEADER' ? 'Header' : `Item ${r.item_no}`}</div></td><td className="value-cell">{r.expected || '—'}</td><td className="value-cell">{r.actual || '—'}</td><td><Status value={r.status}/>{r.status === 'MISMATCH' && <div className="severity-label">{r.severity} severity</div>}</td></tr>)}</tbody></table></div>
              {selected.exceptions?.length > 0 && <div className="exception-note"><div className="exception-note-icon"><AlertTriangle size={17}/></div><div><strong>{selected.exceptions.length} exception{selected.exceptions.length !== 1 ? 's' : ''} identified</strong><p>Differences are flagged for a buyer decision. Values are not written back to SAP.</p></div></div>}
              <div className="approval-block"><div className="approval-heading"><div><h4>Buyer decision</h4><p>Human approval is required when discrepancies exist.</p></div><Status value={selected.approval?.status || 'NOT_REQUIRED'}/></div>
                {selected.approval?.status === 'PENDING' ? <><div className="approval-fields"><label>Reviewer name<input value={reviewer} onChange={e => setReviewer(e.target.value)} placeholder="Enter reviewer name"/></label><label>Decision note<textarea value={comment} onChange={e => setComment(e.target.value)} placeholder="Add reason or supplier context" rows={2}/></label></div><div className="approval-actions"><button className="button danger-outline" disabled={busy || !reviewer.trim() || comment.trim().length < 3} onClick={() => decide('REJECT')}><XCircle size={16}/> Reject confirmation</button><button className="button approve" disabled={busy || !reviewer.trim() || comment.trim().length < 3} onClick={() => decide('APPROVE')}><CheckCircle2 size={16}/> Approve with exceptions</button></div></> : <div className="decision-summary"><div className="decision-icon"><Check size={16}/></div><div><strong>{selected.approval?.status === 'NOT_REQUIRED' ? 'No buyer action required' : `${selected.approval?.status?.replaceAll('_', ' ')} by ${selected.approval?.reviewer}`}</strong><p>{selected.approval?.comment || 'This comparison does not have any open approval actions.'}</p>{selected.approval?.reviewed_at && <span>Reviewed {shortDate(selected.approval.reviewed_at)}</span>}</div></div>}
              </div>
            </> : <div className="empty-detail"><div className="empty-illustration"><GitCompareArrows size={30}/></div><h3>Select a comparison</h3><p>Choose a document comparison from the list, or upload a supplier confirmation to begin.</p><button className="button primary" onClick={() => setUploadOpen(true)}><UploadCloud size={16}/> Upload confirmation</button></div>}
          </section>
        </div>
        <div className="bottom-info"><div><ShieldCheck size={16}/><span><strong>Built for controlled procurement.</strong> Every mismatch is traceable and approval decisions are audited.</span></div><button onClick={() => window.open(`${API}/docs`, '_blank')}><CircleHelp size={15}/> API documentation <ArrowDownToLine size={13}/></button></div>
      </div>
    </main>

    {uploadOpen && <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) setUploadOpen(false) }}><div className="modal"><div className="modal-head"><div><div className="eyebrow">DOCUMENT INTAKE</div><h2>Upload supplier confirmation</h2><p>Compare a text-based supplier PDF with a selected SAP-style purchase order.</p></div><button className="icon-button light" onClick={() => setUploadOpen(false)}><X size={18}/></button></div><form onSubmit={uploadPdf}><label>Purchase order<select value={poNumber} onChange={e => setPoNumber(e.target.value)} required>{orders.map(po => <option key={po.po_number} value={po.po_number}>{po.po_number} · {po.supplier}</option>)}</select></label><label className="file-drop"><input type="file" accept="application/pdf,.pdf" onChange={e => setFile(e.target.files?.[0] || null)} required/><UploadCloud size={26}/><strong>{file ? file.name : 'Choose a PDF confirmation'}</strong><span>{file ? `${(file.size / 1024).toFixed(0)} KB · Ready to compare` : 'PDF format · maximum 15 MB · text-based PDF demo template'}</span></label><div className="modal-tip"><CircleHelp size={15}/><span>Supplier layouts vary. This prototype reads the documented demo template; scanned PDFs need OCR integration.</span></div><div className="modal-actions"><button type="button" className="button secondary" onClick={() => setUploadOpen(false)}>Cancel</button><button className="button primary" type="submit" disabled={busy || !file}>{busy ? 'Processing…' : 'Compare documents'}<ArrowRight size={15}/></button></div></form></div></div>}
  </div>
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App/></React.StrictMode>)
