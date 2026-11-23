import { useEffect, useState } from 'react'
import { Activity, KeyRound, Network, RefreshCw, Shield, Waypoints } from 'lucide-react'

const API = import.meta.env.VITE_CONTROL_API || 'http://localhost:8010'
type Item = Record<string, unknown>
const nav = [
  { id: 'routes', label: 'Routes', icon: Waypoints },
  { id: 'backends', label: 'Backends', icon: Network },
  { id: 'policies', label: 'Policies', icon: Shield },
  { id: 'keys', label: 'API Keys', icon: KeyRound },
  { id: 'traffic', label: 'Live Traffic', icon: Activity },
]

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('adminToken') || 'local-admin-token-change-me')
  const [section, setSection] = useState('routes')
  const [rows, setRows] = useState<Item[]>([])
  const [notice, setNotice] = useState('')
  const [newKey, setNewKey] = useState('')
  async function load() {
    try {
      const r = await fetch(`${API}/api/${section}`, { headers: { 'X-Admin-Token': token } })
      if (!r.ok) throw new Error(await r.text())
      setRows(await r.json()); setNotice('')
    } catch (e) { setNotice(String(e)) }
  }
  useEffect(() => { localStorage.setItem('adminToken', token); void load() }, [section, token])
  async function issueKey() {
    const name = prompt('Name for the new API key?')
    if (!name) return
    const r = await fetch(`${API}/api/keys?name=${encodeURIComponent(name)}`, { method: 'POST', headers: { 'X-Admin-Token': token } })
    if (!r.ok) { setNotice(await r.text()); return }
    const data = await r.json(); setNewKey(data.api_key); await load()
  }
  return <div className="shell">
    <aside><div className="brand"><span className="brandmark">↗</span><div><b>Flowguard</b><small>TRAFFIC CONTROL</small></div></div>
      <div className="nav-label">MANAGEMENT</div>{nav.map(({ id, label, icon: Icon }) => <button key={id} className={`nav-item ${section === id ? 'active' : ''}`} onClick={() => setSection(id)}><Icon size={17}/>{label}</button>)}
      <div className="sidebar-foot"><span className="pulse"/> Gateway environment <b>Development</b></div>
    </aside>
    <main><header><div><p className="eyebrow">INTELLIGENT API TRAFFIC MANAGEMENT</p><h1>{nav.find(n => n.id === section)?.label}</h1></div><div className="header-actions"><input aria-label="Admin token" value={token} onChange={e => setToken(e.target.value)} /><button className="icon-button" onClick={() => void load()} title="Refresh"><RefreshCw size={16}/></button></div></header>
      <section className="summary"><div><span>CONTROL PLANE</span><strong><i/> Connected</strong></div><div><span>VISIBLE RECORDS</span><strong>{rows.length}</strong></div><div><span>REFRESH</span><strong>On demand</strong></div></section>
      {notice && <div className="notice">{notice}</div>}{newKey && <div className="notice key">New key (copy now; it is shown once): <code>{newKey}</code><button onClick={() => setNewKey('')}>Dismiss</button></div>}
      <section className="panel"><div className="panel-head"><div><h2>{section === 'traffic' ? 'Recent requests' : `Configured ${section}`}</h2><p>Changes are loaded by the gateway within a few seconds.</p></div><div>{section === 'keys' && <button className="primary" onClick={() => void issueKey()}>Create API key</button>}<button className="icon-button" onClick={() => void load()}><RefreshCw size={15}/></button></div></div>
        <div className="table-wrap"><table><thead><tr>{(rows[0] ? Object.keys(rows[0]) : ['No records yet']).map(c => <th key={c}>{c.replaceAll('_', ' ')}</th>)}</tr></thead><tbody>{rows.map((row, i) => <tr key={String(row.id || row.request_id || i)}>{Object.entries(row).map(([key, value]) => <td key={key}>{key === 'is_active' || key === 'active' ? <span className={`badge ${value ? 'good' : 'muted'}`}>{String(value)}</span> : typeof value === 'object' ? JSON.stringify(value) : String(value ?? '—')}</td>)}</tr>)}</tbody></table>{!rows.length && <div className="empty">No records to show.</div>}</div>
      </section>
      <footer><span><i/> Redis · PostgreSQL · Gateway</span><span>Flowguard <b>v0.1</b></span></footer>
    </main>
  </div>
}
