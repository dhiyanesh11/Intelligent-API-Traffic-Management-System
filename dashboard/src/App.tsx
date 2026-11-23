import { useEffect, useState } from 'react'
import { Activity, KeyRound, Network, Plus, RefreshCw, Shield, Trash2, Waypoints } from 'lucide-react'

const API = import.meta.env.VITE_CONTROL_API || 'http://localhost:8010'
type Item = Record<string, unknown>
const nav = [
  { id: 'routes', label: 'Routes', icon: Waypoints },
  { id: 'backends', label: 'Backends', icon: Network },
  { id: 'policies', label: 'Policies', icon: Shield },
  { id: 'keys', label: 'API Keys', icon: KeyRound },
  { id: 'traffic', label: 'Live Traffic', icon: Activity },
  { id: 'whitelist', label: 'Whitelist', icon: Shield },
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
  async function mutate(path: string, method: string, body?: unknown) {
    const r = await fetch(`${API}${path}`, { method, headers: { 'X-Admin-Token': token, ...(body ? { 'Content-Type': 'application/json' } : {}) }, body: body ? JSON.stringify(body) : undefined })
    if (!r.ok) { setNotice(await r.text()); return }
    setNotice('Saved. Gateway configuration refreshes automatically.'); await load()
  }
  async function createItem() {
    if (section === 'routes') {
      const name = prompt('Route name?'); if (!name) return
      const path_prefix = prompt('Path prefix?', '/new'); if (!path_prefix) return
      const backend_id = Number(prompt('Backend ID?', '1') || 1)
      const policy_id = Number(prompt('Rate policy ID?', '1') || 1)
      await mutate('/api/routes', 'POST', { name, path_prefix, methods: ['GET', 'POST'], backend_id, policy_id, auth_required: true, strategy: 'round_robin', is_active: true })
    } else if (section === 'backends') {
      const name = prompt('Backend name?'); if (!name) return
      const base_url = prompt('Backend base URL?'); if (!base_url) return
      await mutate('/api/backends', 'POST', { name, base_url, weight: 1, is_active: true })
    } else if (section === 'policies') {
      const name = prompt('Policy name?'); if (!name) return
      const limit = Number(prompt('Requests per window?', '60') || 60)
      await mutate('/api/policies', 'POST', { name, algorithm: 'token_bucket', limit, window_seconds: 60, scope: 'api_key', is_active: true })
    } else if (section === 'whitelist') {
      const client = prompt('Client IP or principal to whitelist?'); if (client) await mutate('/api/whitelist', 'POST', { client })
    }
  }
  async function rowAction(row: Item, action: string) {
    const id = String(row.id || '')
    if (action === 'delete' && section === 'routes') await mutate(`/api/routes/${id}`, 'DELETE')
    if (action === 'delete' && section === 'keys') await mutate(`/api/keys/${id}`, 'DELETE')
    if (action === 'delete' && section === 'whitelist') await mutate(`/api/whitelist/${encodeURIComponent(String(row.client))}`, 'DELETE')
    if (action === 'edit' && section === 'routes') {
      const path_prefix = prompt('Path prefix?', String(row.path_prefix)); if (path_prefix) await mutate(`/api/routes/${id}`, 'PUT', { ...row, path_prefix })
    }
    if (action === 'override' && section === 'policies') {
      const limit = Number(prompt('Temporary requests per window?', String(row.limit)) || 0); if (!limit) return
      const ttl_seconds = Number(prompt('Override lifetime in seconds (0 = no expiry)?', '3600') || 3600)
      await mutate(`/api/policies/${id}/override`, 'PUT', { limit, ttl_seconds })
    }
  }
  return <div className="shell">
    <aside><div className="brand"><span className="brandmark">↗</span><div><b>Flowguard</b><small>TRAFFIC CONTROL</small></div></div>
      <div className="nav-label">MANAGEMENT</div>{nav.map(({ id, label, icon: Icon }) => <button key={id} className={`nav-item ${section === id ? 'active' : ''}`} onClick={() => setSection(id)}><Icon size={17}/>{label}</button>)}
      <div className="sidebar-foot"><span className="pulse"/> Gateway environment <b>Development</b></div>
    </aside>
    <main><header><div><p className="eyebrow">INTELLIGENT API TRAFFIC MANAGEMENT</p><h1>{nav.find(n => n.id === section)?.label}</h1></div><div className="header-actions"><input aria-label="Admin token" value={token} onChange={e => setToken(e.target.value)} /><button className="icon-button" onClick={() => void load()} title="Refresh"><RefreshCw size={16}/></button></div></header>
      <section className="summary"><div><span>CONTROL PLANE</span><strong><i/> Connected</strong></div><div><span>VISIBLE RECORDS</span><strong>{rows.length}</strong></div><div><span>REFRESH</span><strong>On demand</strong></div></section>
      {notice && <div className="notice">{notice}</div>}{newKey && <div className="notice key">New key (copy now; it is shown once): <code>{newKey}</code><button onClick={() => setNewKey('')}>Dismiss</button></div>}
      <section className="panel"><div className="panel-head"><div><h2>{section === 'traffic' ? 'Recent requests' : `Configured ${section}`}</h2><p>Changes are loaded by the gateway within a few seconds.</p></div><div>{['routes','backends','policies','whitelist'].includes(section) && <button className="primary" onClick={() => void createItem()}><Plus size={14}/> Add</button>}{section === 'keys' && <button className="primary" onClick={() => void issueKey()}>Create API key</button>}<button className="icon-button" onClick={() => void load()}><RefreshCw size={15}/></button></div></div>
        <div className="table-wrap"><table><thead><tr>{(rows[0] ? Object.keys(rows[0]) : ['No records yet']).map(c => <th key={c}>{c.replaceAll('_', ' ')}</th>)}{['routes','keys','whitelist','policies'].includes(section) && <th>Actions</th>}</tr></thead><tbody>{rows.map((row, i) => <tr key={String(row.id || row.request_id || row.client || i)}>{Object.entries(row).map(([key, value]) => <td key={key}>{key === 'is_active' || key === 'active' || key === 'whitelisted' ? <span className={`badge ${value ? 'good' : 'muted'}`}>{String(value)}</span> : typeof value === 'object' ? JSON.stringify(value) : String(value ?? '—')}</td>)}{section === 'routes' && <td><button className="icon-button" onClick={() => void rowAction(row,'edit')}>Edit</button> <button className="icon-button" onClick={() => void rowAction(row,'delete')}><Trash2 size={14}/></button></td>}{section === 'keys' && <td><button className="icon-button" onClick={() => void rowAction(row,'delete')}>Revoke</button></td>}{section === 'whitelist' && <td><button className="icon-button" onClick={() => void rowAction(row,'delete')}>Remove</button></td>}{section === 'policies' && <td><button className="icon-button" onClick={() => void rowAction(row,'override')}>Override</button></td>}</tr>)}</tbody></table>{!rows.length && <div className="empty">No records to show.</div>}</div>
      </section>
      <footer><span><i/> Redis · PostgreSQL · Gateway</span><span>Flowguard <b>v0.1</b></span></footer>
    </main>
  </div>
}
