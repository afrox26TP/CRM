import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, ArrowRight, BarChart3, Check, CheckCircle2, ChevronDown,
  CircleDollarSign, Download, FileCheck2, FileSpreadsheet, FileText, Filter,
  LayoutDashboard, Menu, Plus, ReceiptText, RefreshCw, Search, Settings,
  Sparkles, Truck, Upload, Users, X,
} from 'lucide-react'
import brandLogo from './assets/crm-logo.png'

const API = import.meta.env.VITE_API_URL || '/api'
const statusMeta = {
  received: ['Přijato', 'neutral'], processing: ['AI zpracovává', 'info'], matched: ['Spárováno', 'success'],
  needs_review: ['Ke kontrole', 'warning'], approved: ['Schváleno', 'success'], exported: ['Exportováno', 'violet'],
}
const typeMeta = { cmr: ['CMR', 'blue'], tax: ['Daňový doklad', 'orange'], unknown: ['Nerozpoznáno', 'neutral'] }

function BrandLogo() {
  return <span className="brand-mark"><img src={brandLogo} alt="Conpath logo" className="brand-logo-full" /></span>
}

const money = (value, currency = 'CZK') => value == null ? '—' : new Intl.NumberFormat('cs-CZ', { style: 'currency', currency, maximumFractionDigits: 2 }).format(Number(value))
const dateValue = (value) => value ? new Intl.DateTimeFormat('cs-CZ').format(new Date(value)) : '—'

async function request(path, options) {
  const response = await fetch(`${API}${path}`, {
    credentials: 'include',
    ...options,
    headers: { ...(options?.headers || {}) },
  })
  if (!response.ok) {
    let message = 'Požadavek se nezdařil.'
    try { message = (await response.json()).detail || message } catch { /* non-JSON response */ }
    throw new Error(message)
  }
  return response.headers.get('content-type')?.includes('json') ? response.json() : response
}

function LoginGate({ onLoggedIn }) {
  const [pin, setPin] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    setBusy(true); setError('')
    try {
      const session = await request('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin }),
      })
      onLoggedIn(session)
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  return <div className="login-shell"><section className="login-card"><div className="brand login-brand"><BrandLogo /></div><div className="login-form"><input className="login-pin" type="password" inputMode="numeric" pattern="[0-9]*" value={pin} onChange={e => setPin(e.target.value.replace(/\D/g, ''))} placeholder="Zadejte PIN" /><button className="primary" disabled={!pin || busy} onClick={submit}>{busy ? 'Přihlašuji…' : 'Přihlásit'}</button></div>{error && <div className="error-box"><AlertTriangle size={17} />{error}</div>}</section></div>
}

function Badge({ value, map }) {
  const [label, tone] = map[value] || [value, 'neutral']
  return <span className={`badge badge-${tone}`}><i />{label}</span>
}

function Sidebar({ active, onChange, open, onClose, onLogout }) {
  const items = [
    ['dashboard', LayoutDashboard, 'Přehled'], ['documents', FileText, 'Doklady'],
    ['transports', Truck, 'Přepravy'], ['accounting', CircleDollarSign, 'Účetnictví'],
  ]
  return <>
    {open && <button className="sidebar-scrim" onClick={onClose} aria-label="Zavřít nabídku" />}
    <aside className={`sidebar ${open ? 'is-open' : ''}`}>
      <div className="brand"><BrandLogo /></div>
      <nav aria-label="Hlavní navigace">
        <p className="nav-caption">Pracovní prostor</p>
        {items.map(([id, Icon, label]) => <button key={id} className={active === id ? 'active' : ''} onClick={() => { onChange(id); onClose() }}><Icon size={19} />{label}</button>)}
        <p className="nav-caption nav-spaced">Správa</p>
        <button onClick={() => { onChange('settings'); onClose() }} className={active === 'settings' ? 'active' : ''}><Settings size={19} />Nastavení</button>
      </nav>
      <div className="ai-card"><span><Sparkles size={16} /> AI modul</span><strong>Google Document AI</strong><small>Připraveno ke zpracování</small><div><i /></div></div>
      <button className="sidebar-user role-switch" onClick={onLogout}><span>VR</span><div><strong>Vratislav</strong><small>Jednatel · odhlásit</small></div><ChevronDown size={16} /></button>
    </aside>
  </>
}

function Header({ title, onMenu, onUpload }) {
  return <header><button className="icon-button mobile-menu" onClick={onMenu}><Menu /></button><div><p>Sekce</p><h1>{title}</h1></div><div className="header-actions"><button className="icon-button" aria-label="Obnovit" onClick={() => location.reload()}><RefreshCw size={18} /></button><button className="primary" onClick={onUpload}><Plus size={18} />Nahrát doklady</button></div></header>
}

function Metric({ icon: Icon, label, value, note, tone, progress }) {
  return <article className="metric"><div className={`metric-icon ${tone}`}><Icon size={21} /></div><div className="metric-copy"><p>{label}</p><strong>{value}</strong>{progress != null ? <div className="metric-progress"><span style={{ width: `${progress}%` }} /></div> : <small>{note}</small>}</div>{progress != null && <em>{progress}%</em>}</article>
}

function Dashboard({ data, documents, setPage, selectDocument }) {
  const recent = documents.slice(0, 5)
  const team = Object.entries(data.by_dispatcher || {})
  return <>
    <section className="welcome"><div><span className="eyebrow"><Sparkles size={14} /> Automatizace běží</span><h2>Dobrý den, Vratislave</h2><p>Tady je celkový stav zpracování dokladů a práce týmu.</p></div><div className="welcome-graphic"><Truck size={40} /><span><Check size={16} /></span></div></section>
    <section className="metrics-grid">
      <Metric icon={FileText} label="Doklady celkem" value={data.documents_total ?? '—'} note="v evidenci" tone="blue" />
      <Metric icon={FileCheck2} label="Úspěšně spárováno" value={data.matched ?? '—'} note="bez ruční práce" tone="green" />
      <Metric icon={AlertTriangle} label="Čeká na kontrolu" value={data.needs_review ?? '—'} note="vyžaduje pozornost" tone="amber" />
      <Metric icon={Sparkles} label="Míra automatizace" value="" progress={data.automation_rate ?? 0} tone="violet" />
    </section>
    <section className="dashboard-grid">
      <div className="panel recent-panel"><div className="panel-heading"><div><h3>Poslední doklady</h3><p>Nejnovější příchozí dokumenty</p></div><button className="link-button" onClick={() => setPage('documents')}>Zobrazit vše <ArrowRight size={16} /></button></div><DocumentTable documents={recent} compact selectDocument={selectDocument} /></div>
      <div className="panel team-panel"><div className="panel-heading"><div><h3>Vytížení řidičů</h3><p>Doklady podle řidiče kamionu</p></div></div>{team.length ? team.map(([name, count], index) => <div className="team-row" key={name}><span className={`avatar avatar-${index % 3}`}>{name[0]}{name.slice(-1)}</span><div><strong>{name}</strong><small>{count} dokladů</small></div><div className="team-bar"><span style={{ width: `${Math.min(100, Number(count) * 18 + 12)}%` }} /></div><b>{count}</b></div>) : <div className="empty"><Users /><strong>Zatím nejsou přidaní řidiči</strong><p>Přidejte je v nastavení.</p></div>}<div className="team-total"><CircleDollarSign size={20} /><div><small>Schválené náklady</small><strong>{money(data.approved_tax_total)}</strong></div></div></div>
    </section>
  </>
}

function DocumentTable({ documents, compact = false, selectDocument }) {
  if (!documents.length) return <div className="empty"><FileText /><strong>Žádné doklady</strong><p>Změňte filtr nebo nahrajte první dokument.</p></div>
  return <div className="table-wrap"><table><thead><tr><th>Doklad</th><th>Typ</th><th>Stav</th>{!compact && <th>Řidič</th>}<th>Datum</th><th></th></tr></thead><tbody>{documents.map(doc => <tr key={doc.id} onClick={() => selectDocument(doc)}><td><div className="file-cell"><span className={doc.document_type === 'tax' ? 'tax-file' : ''}>{doc.document_type === 'tax' ? <ReceiptText size={19} /> : <FileText size={19} />}</span><div><strong>{doc.cmr_number || doc.supplier || doc.original_name}</strong><small>{doc.original_name}</small></div></div></td><td><Badge value={doc.document_type} map={typeMeta} /></td><td><Badge value={doc.status} map={statusMeta} /></td>{!compact && <td>{doc.dispatcher || '—'}</td>}<td>{dateValue(doc.issue_date || doc.created_at)}</td><td><button className="row-action" aria-label="Otevřít"><ArrowRight size={17} /></button></td></tr>)}</tbody></table></div>
}

function Documents({ documents, loading, filters, setFilters, selectDocument }) {
  return <section className="panel page-panel"><div className="panel-heading docs-heading"><div><h3>Doklady</h3><p>{documents.length} položek podle zvolených filtrů</p></div><div className="view-toggle"><button className="active"><FileText size={16} /></button><button><BarChart3 size={16} /></button></div></div><div className="filters"><label className="search"><Search size={17} /><input value={filters.search} onChange={e => setFilters({ ...filters, search: e.target.value })} placeholder="Hledat CMR, dodavatele…" /></label><select value={filters.type} onChange={e => setFilters({ ...filters, type: e.target.value })}><option value="">Všechny typy</option><option value="cmr">CMR</option><option value="tax">Daňové doklady</option></select><select value={filters.status} onChange={e => setFilters({ ...filters, status: e.target.value })}><option value="">Všechny stavy</option>{Object.entries(statusMeta).map(([key, [label]]) => <option key={key} value={key}>{label}</option>)}</select><button className="filter-button"><Filter size={16} />Další filtry</button></div>{loading ? <div className="loading"><RefreshCw /> Načítám…</div> : <DocumentTable documents={documents} selectDocument={selectDocument} />}</section>
}

function Transports({ transports, onImport }) {
  return <section className="panel page-panel"><div className="panel-heading"><div><h3>Přepravy z Konspedu</h3><p>Importované zakázky připravené k párování</p></div><button className="secondary" onClick={onImport}><FileSpreadsheet size={17} />Importovat Excel</button></div><div className="table-wrap"><table><thead><tr><th>Číslo CMR</th><th>Řidič / SPZ</th><th>Trasa</th><th>Datum</th><th>Cena</th><th>Řidič kamionu</th><th>Doklady</th></tr></thead><tbody>{transports.map(item => <tr key={item.id}><td><strong>{item.cmr_number}</strong></td><td><div className="stack"><strong>{item.driver_name || '—'}</strong><small>{item.license_plate || '—'}</small></div></td><td>{item.route || '—'}</td><td>{dateValue(item.transport_date)}</td><td><strong>{money(item.transport_price, item.currency)}</strong></td><td>{item.dispatcher || '—'}</td><td><span className="count-pill">{item.document_count}</span></td></tr>)}</tbody></table></div></section>
}

function Accounting({ documents, onExport }) {
  const approved = documents.filter(d => ['approved', 'exported'].includes(d.status) && d.document_type === 'tax')
  const total = approved.reduce((sum, item) => sum + Number(item.gross_amount || 0), 0)
  return <><section className="accounting-hero"><div className="metric-icon green"><CircleDollarSign /></div><div><p>Schválené náklady</p><strong>{money(total)}</strong><small>{approved.length} dokladů připravených pro účetnictví</small></div><button className="primary" onClick={onExport}><Download size={18} />Exportovat CSV</button></section><section className="panel page-panel"><div className="panel-heading"><div><h3>Daňové doklady</h3><p>Zkontrolované částky DPH a základu daně</p></div></div><DocumentTable documents={approved} selectDocument={() => {}} /></section></>
}

function SettingsPage({ employees, onEmployeeAdded }) {
  const [name, setName] = useState('')
  const [pin, setPin] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const addEmployee = async () => {
    setBusy(true); setError('')
    try {
      await request('/employees', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), pin }),
      })
      setName('')
      setPin('')
      onEmployeeAdded()
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  return <section className="settings-grid"><div className="panel settings-card"><div className="settings-icon"><Users /></div><h3>Přidat řidiče</h3><div className="login-form"><input value={name} onChange={e => setName(e.target.value)} placeholder="Jméno řidiče" /><input value={pin} onChange={e => setPin(e.target.value.replace(/\D/g, ''))} maxLength={4} placeholder="4místný PIN" /><button className="primary" disabled={busy || !name.trim() || pin.length !== 4} onClick={addEmployee}>{busy ? 'Ukládám…' : 'Přidat řidiče'}</button></div>{error && <div className="error-box"><AlertTriangle size={17} />{error}</div>}</div><div className="panel settings-card"><div className="settings-icon"><FileSpreadsheet /></div><h3>Seznam řidičů</h3>{employees.length ? <div className="employee-list">{employees.map(item => <article key={item.user_id}><span><Users size={18} /></span><div><strong>{item.name}</strong><small>ID: {item.user_id}</small></div></article>)}</div> : <div className="empty"><Users /><strong>Žádní řidiči</strong><p>Přidejte prvního řidiče.</p></div>}</div><div className="panel settings-card"><div className="settings-icon"><Sparkles /></div><h3>Google Document AI</h3><p>Cloudové vytěžování CMR, faktur a účtenek.</p><div className="connection"><i /> Připojení se ověřuje na backendu</div></div></section>
}

function UploadModal({ onClose, onDone, mode = 'documents' }) {
  const input = useRef(null)
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const isImport = mode === 'transports'
  const submit = async () => {
    if (!files.length) return
    setBusy(true); setError('')
    const form = new FormData()
    files.forEach(file => form.append(isImport ? 'file' : 'files', file))
    try { await request(isImport ? '/transports/import' : '/documents/upload', { method: 'POST', body: form }); onDone() }
    catch (err) { setError(err.message); setBusy(false) }
  }
  return <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}><div className="modal"><button className="modal-close" onClick={onClose}><X /></button><span className="modal-icon"><Upload /></span><h2>{isImport ? 'Importovat přepravy' : 'Nahrát nové doklady'}</h2><p>{isImport ? 'Vyberte aktuální tabulku z Konspedu.' : 'AI automaticky rozpozná CMR, fakturu nebo účtenku.'}</p><button className="dropzone" onClick={() => input.current.click()} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); setFiles([...e.dataTransfer.files]) }}><Upload /><strong>Přetáhněte soubory sem</strong><span>nebo klikněte pro výběr</span><small>{isImport ? 'XLSX, XLS nebo CSV · max. 25 MB' : 'JPG, PNG, WebP nebo PDF · max. 15 MB'}</small></button><input ref={input} hidden type="file" multiple={!isImport} accept={isImport ? '.xlsx,.xls,.csv' : 'image/jpeg,image/png,image/webp,application/pdf'} onChange={e => setFiles([...e.target.files])} />{files.length > 0 && <div className="selected-files">{files.map(file => <span key={file.name}><FileText size={15} />{file.name}<Check size={15} /></span>)}</div>}{error && <div className="error-box"><AlertTriangle size={17} />{error}</div>}<div className="modal-actions"><button className="secondary" onClick={onClose}>Zrušit</button><button className="primary" disabled={!files.length || busy} onClick={submit}>{busy ? <RefreshCw className="spin" size={17} /> : <Sparkles size={17} />}{busy ? 'Zpracovávám…' : isImport ? 'Importovat' : 'Spustit AI zpracování'}</button></div></div></div>
}

function DetailDrawer({ document, onClose, onSaved, employees }) {
  const [form, setForm] = useState(document)
  const [busy, setBusy] = useState(false)
  const set = (key, value) => setForm(old => ({ ...old, [key]: value }))
  const save = async status => { setBusy(true); try { await request(`/documents/${document.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ document_type: form.document_type, cmr_number: form.cmr_number || null, issue_date: form.issue_date || null, supplier: form.supplier || null, net_amount: form.net_amount === '' ? null : form.net_amount, vat_amount: form.vat_amount === '' ? null : form.vat_amount, gross_amount: form.gross_amount === '' ? null : form.gross_amount, dispatcher: form.dispatcher || null, status }) }); onSaved() } finally { setBusy(false) } }
  return <div className="drawer-backdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}><aside className="drawer"><div className="drawer-head"><div><Badge value={document.status} map={statusMeta} /><h2>Kontrola dokladu</h2><p>{document.original_name}</p></div><button className="icon-button" onClick={onClose}><X /></button></div><div className="confidence"><Sparkles size={18} /><div><strong>AI jistota {Math.round(Number(document.confidence || 0) * 100)} %</strong><span>Ověřte označené hodnoty před schválením.</span></div></div><div className="form-grid"><label>Typ dokladu<select value={form.document_type} onChange={e => set('document_type', e.target.value)}><option value="cmr">CMR</option><option value="tax">Daňový doklad</option><option value="unknown">Nerozpoznáno</option></select></label>{form.document_type === 'cmr' ? <label>Číslo CMR<input value={form.cmr_number || ''} onChange={e => set('cmr_number', e.target.value)} /></label> : <><label className="wide">Dodavatel<input value={form.supplier || ''} onChange={e => set('supplier', e.target.value)} /></label><label>Datum vystavení<input type="date" value={form.issue_date || ''} onChange={e => set('issue_date', e.target.value)} /></label><label>Základ DPH<input type="number" value={form.net_amount || ''} onChange={e => set('net_amount', e.target.value)} /></label><label>DPH<input type="number" value={form.vat_amount || ''} onChange={e => set('vat_amount', e.target.value)} /></label><label>Celkem s DPH<input type="number" value={form.gross_amount || ''} onChange={e => set('gross_amount', e.target.value)} /></label></>}<label>Řidič kamionu<select value={form.dispatcher || ''} onChange={e => set('dispatcher', e.target.value)}><option value="">Nepřiřazeno</option>{employees.map((item) => <option key={item.user_id} value={item.name}>{item.name}</option>)}</select></label></div>{document.transport_id && <div className="match-box"><CheckCircle2 /><div><strong>Spárováno s přepravou</strong><span>Konsped · ID {document.transport_id}</span></div></div>}<div className="drawer-actions"><button className="secondary" onClick={onClose}>Zavřít</button><button className="primary" disabled={busy} onClick={() => save('approved')}><Check size={18} />Schválit doklad</button></div></aside></div>
}

function EmployeePortal({ session, onLogout }) {
  const today = new Date().toISOString().slice(0, 10)
  const monthStart = `${today.slice(0, 8)}01`
  const [range, setRange] = useState({ from: monthStart, to: today })
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [upload, setUpload] = useState(false)

  const loadMine = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const params = new URLSearchParams({ date_from: range.from, date_to: range.to })
      setDocuments(await request(`/me/documents?${params}`))
    } catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }, [range])

  useEffect(() => { const timer = setTimeout(loadMine, 0); return () => clearTimeout(timer) }, [loadMine])

  const firstName = (session.name || 'Řidič').split(' ')[0]

  return <div className="employee-shell">
    <header className="employee-header"><div className="brand employee-brand"><BrandLogo /></div><button className="employee-profile" onClick={onLogout}><span>{session.name?.split(' ').map(v => v[0]).join('') || 'RK'}</span><div><strong>{session.name || 'Řidič'}</strong><small>Řidič kamionu · odhlásit</small></div><ChevronDown size={16} /></button></header>
    <main className="employee-main"><section className="employee-welcome"><div><span className="eyebrow"><CheckCircle2 size={14} /> Osobní prostor</span><h1>Dobrý den, {firstName}</h1><p>Nahrajte fotografie dokladů a zkontrolujte svůj vlastní výpis.</p></div><button className="employee-upload" onClick={() => setUpload(true)}><Upload size={26} /><span><strong>Nahrát fotografie</strong><small>JPG, PNG, WebP nebo PDF</small></span><ArrowRight size={20} /></button></section>
      <section className="panel employee-statement"><div className="panel-heading employee-heading"><div><h3>Můj výpis dokladů</h3><p>Vidíte pouze dokumenty, které jste nahrál vy.</p></div><div className="date-range"><label>Od<input type="date" value={range.from} onChange={e => setRange({ ...range, from: e.target.value })} /></label><label>Do<input type="date" value={range.to} onChange={e => setRange({ ...range, to: e.target.value })} /></label></div></div>
        {error && <div className="api-warning"><AlertTriangle /><div><strong>Výpis nelze načíst</strong><span>{error}</span></div></div>}
        {loading ? <div className="loading"><RefreshCw /> Načítám váš výpis…</div> : documents.length ? <div className="employee-list">{documents.map(doc => <article key={doc.id}><span className={doc.document_type === 'tax' ? 'tax-file' : ''}>{doc.document_type === 'tax' ? <ReceiptText /> : <FileText />}</span><div><strong>{doc.cmr_number || doc.original_name}</strong><small>{doc.original_name} · nahráno {dateValue(doc.created_at)}</small></div><Badge value={doc.document_type} map={typeMeta} /><Badge value={doc.status} map={statusMeta} /></article>)}</div> : <div className="empty"><ReceiptText /><strong>V tomto období nemáte žádné doklady</strong><p>Nahrajte fotografie nebo změňte rozsah data.</p></div>}
      </section>
    </main>
    {upload && <UploadModal onClose={() => setUpload(false)} onDone={() => { setUpload(false); loadMine() }} />}
  </div>
}

export default function App() {
  const [session, setSession] = useState(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [page, setPage] = useState('dashboard')
  const [menu, setMenu] = useState(false)
  const [upload, setUpload] = useState(null)
  const [selected, setSelected] = useState(null)
  const [dashboard, setDashboard] = useState({})
  const [documents, setDocuments] = useState([])
  const [transports, setTransports] = useState([])
  const [employees, setEmployees] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [driver, setDriver] = useState('Všichni')
  const [filters, setFilters] = useState({ search: '', status: '', type: '' })
  const ownerDrivers = useMemo(() => ['Všichni', ...employees.map((item) => item.name)], [employees])
  const titles = { dashboard: 'Přehled', documents: 'Doklady', transports: 'Přepravy', accounting: 'Účetnictví', settings: 'Nastavení' }

  useEffect(() => {
    const checkSession = async () => {
      try { setSession(await request('/auth/session')) }
      catch { setSession(null) }
      finally { setAuthLoading(false) }
    }
    checkSession()
  }, [])

  const load = useCallback(async () => {
    if (session?.role !== 'owner') { setLoading(false); return }
    setLoading(true); setError('')
    try {
      const params = new URLSearchParams()
      if (driver !== 'Všichni') params.set('dispatcher', driver)
      if (filters.status) params.set('status', filters.status)
      if (filters.type) params.set('type', filters.type)
      if (filters.search) params.set('search', filters.search)
      const [dash, docs, trips, staff] = await Promise.all([request('/dashboard'), request(`/documents?${params}`), request('/transports'), request('/employees')])
      setDashboard(dash); setDocuments(docs); setTransports(trips); setEmployees(staff)
    } catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }, [driver, filters, session?.role])

  useEffect(() => { const timer = setTimeout(load, filters.search ? 250 : 0); return () => clearTimeout(timer) }, [load, filters.search])
  const completeModal = () => { setUpload(null); load() }
  const completeDrawer = () => { setSelected(null); load() }
  const logout = async () => {
    try { await request('/auth/logout', { method: 'POST' }) }
    finally {
      setSession(null)
      setPage('dashboard')
      setDriver('Všichni')
      setSelected(null)
      setUpload(null)
    }
  }
  const exportAccounting = useCallback(async () => {
    try {
      const response = await request('/accounting/export.csv')
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `ucetnictvi-${new Date().toISOString().slice(0, 10)}.csv`
      link.click()
      URL.revokeObjectURL(url)
      load()
    } catch (err) { setError(err.message) }
  }, [load])
  const content = useMemo(() => {
    if (page === 'dashboard') return <Dashboard data={dashboard} documents={documents} setPage={setPage} selectDocument={setSelected} />
    if (page === 'documents') return <Documents documents={documents} loading={loading} filters={filters} setFilters={setFilters} selectDocument={setSelected} />
    if (page === 'transports') return <Transports transports={transports} onImport={() => setUpload('transports')} />
    if (page === 'accounting') return <Accounting documents={documents} onExport={exportAccounting} />
    return <SettingsPage employees={employees} onEmployeeAdded={load} />
  }, [page, dashboard, documents, transports, loading, filters, exportAccounting, employees, load])

  if (authLoading) return <div className="loading"><RefreshCw /> Ověřuji přihlášení…</div>
  if (!session) return <LoginGate onLoggedIn={(payload) => { setSession(payload); setPage('dashboard'); setDriver('Všichni') }} />
  if (session.role === 'employee') return <EmployeePortal session={session} onLogout={logout} />

  return <div className="app-shell"><Sidebar active={page} onChange={setPage} open={menu} onClose={() => setMenu(false)} onLogout={logout} /><main><Header title={titles[page]} onMenu={() => setMenu(true)} onUpload={() => setUpload('documents')} /><div className="dispatcher-tabs"><span>Řidič:</span>{ownerDrivers.map(name => <button key={name} className={driver === name ? 'active' : ''} onClick={() => setDriver(name)}>{name}{name !== 'Všichni' && <b>{dashboard.by_dispatcher?.[name] || 0}</b>}</button>)}</div><div className="content">{error && <div className="api-warning"><AlertTriangle /><div><strong>Backend není dostupný</strong><span>{error} Spusťte FastAPI server podle README.</span></div><button onClick={load}>Zkusit znovu</button></div>}{content}</div></main>{upload && <UploadModal mode={upload} onClose={() => setUpload(null)} onDone={completeModal} />}{selected && <DetailDrawer document={selected} employees={employees} onClose={() => setSelected(null)} onSaved={completeDrawer} />}</div>
}
