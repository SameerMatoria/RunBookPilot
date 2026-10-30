import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import { SessionContext, useSession } from './session.jsx'
import Login from './components/Login.jsx'
import RunbookList from './components/RunbookList.jsx'
import RunbookDetail from './components/RunbookDetail.jsx'
import Dashboard from './components/Dashboard.jsx'
import { AuditPage, UsersPage } from './components/Admin.jsx'
import { ServersPage } from './components/Servers.jsx'
import { RunDetail, RunsPage } from './components/Runs.jsx'

function useHashRoute() {
  const [hash, setHash] = useState(window.location.hash)
  useEffect(() => {
    const onChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  let m
  if ((m = hash.match(/^#\/runbooks\/([\w-]+)/))) return { page: 'runbook', id: m[1] }
  if ((m = hash.match(/^#\/runs\/(\d+)/))) return { page: 'run', id: Number(m[1]) }
  const page = hash.replace(/^#\//, '').split(/[/?]/)[0]
  return { page: ['impact', 'runs', 'servers', 'users', 'audit'].includes(page) ? page : 'runbooks' }
}

function SystemStatus() {
  const [health, setHealth] = useState(null)
  const [sandbox, setSandbox] = useState(null)
  useEffect(() => {
    const load = () => {
      api.health().then(setHealth).catch(() => setHealth({ ok: false }))
      api.sandbox().then(setSandbox).catch(() => setSandbox({ ready: false, workers: 0 }))
    }
    load()
    const timer = setInterval(load, 30000)
    return () => clearInterval(timer)
  }, [])
  const sandboxLabel = !sandbox
    ? 'Sandbox…'
    : sandbox.ready
      ? `Sandbox ready${sandbox.workers > 1 ? ` · ${sandbox.workers} workers` : ''}`
      : sandbox.workers === 0
        ? 'No worker running'
        : 'Sandbox offline'
  return (
    <div className="system-status">
      <span className={`dot ${health?.key_configured ? 'on' : health ? 'off' : ''}`} />
      <span>{health?.model ?? 'API…'}</span>
      <span className={`dot ${sandbox?.ready ? 'on' : sandbox ? 'off' : ''}`} />
      <span title={sandbox?.detail}>{sandboxLabel}</span>
    </div>
  )
}

function UserMenu() {
  const { user, signOut } = useSession()
  const [open, setOpen] = useState(false)
  const initials = user.display_name
    .split(/\s+/)
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
  return (
    <div className="user-menu">
      <button className="avatar" onClick={() => setOpen(!open)} aria-expanded={open} aria-label="Account menu">
        {initials}
      </button>
      {open && (
        <div className="menu" onMouseLeave={() => setOpen(false)}>
          <div className="strong">{user.display_name}</div>
          <div className="muted small">{user.username}</div>
          <div className="menu-roles">
            {user.roles.map((r) => (
              <span key={r} className="tag">
                {r}
              </span>
            ))}
          </div>
          <button className="btn btn-ghost btn-small" onClick={signOut}>
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}

function Shell() {
  const route = useHashRoute()
  const { can } = useSession()
  const nav = [
    ['runbooks', 'Runbooks', true],
    ['runs', 'Runs', true],
    ['impact', 'Impact', true],
    ['servers', 'Servers', can('operator')],
    ['users', 'Users', can('admin')],
    ['audit', 'Audit', can('admin')],
  ]
  const current = route.page === 'runbook' ? 'runbooks' : route.page === 'run' ? 'runs' : route.page

  const pages = {
    runbooks: <RunbookList />,
    runbook: <RunbookDetail id={route.id} />,
    runs: <RunsPage />,
    run: <RunDetail id={route.id} />,
    impact: <Dashboard />,
    servers: <ServersPage />,
    users: <UsersPage />,
    audit: <AuditPage />,
  }

  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#/">
          <span className="brand-mark" aria-hidden="true" />
          RunbookPilot
        </a>
        <nav className="nav">
          {nav
            .filter(([, , show]) => show)
            .map(([page, label]) => (
              <a key={page} href={`#/${page === 'runbooks' ? '' : page}`} className={current === page ? 'active' : ''}>
                {label}
              </a>
            ))}
        </nav>
        <SystemStatus />
        <UserMenu />
      </header>
      <main className="content">{pages[route.page]}</main>
    </div>
  )
}

export default function App() {
  const [user, setUser] = useState(undefined) // undefined = still checking, null = signed out

  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null))
    const onUnauthorized = () => setUser(null)
    window.addEventListener('rbp:unauthorized', onUnauthorized)
    return () => window.removeEventListener('rbp:unauthorized', onUnauthorized)
  }, [])

  const signOut = useCallback(async () => {
    await api.logout().catch(() => {})
    setUser(null)
  }, [])

  if (user === undefined) return <div className="login-page muted">Loading…</div>
  if (user === null) return <Login onSignedIn={setUser} />
  return (
    <SessionContext.Provider value={{ user, signOut }}>
      <Shell />
    </SessionContext.Provider>
  )
}
