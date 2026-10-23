import { useEffect, useState } from 'react'
import { api } from './api.js'
import RunbookList from './components/RunbookList.jsx'
import RunbookDetail from './components/RunbookDetail.jsx'

function useHashRoute() {
  const [hash, setHash] = useState(window.location.hash)
  useEffect(() => {
    const onChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  const match = hash.match(/^#\/runbooks\/([\w-]+)/)
  return match ? { page: 'detail', id: match[1] } : { page: 'list' }
}

function SystemStatus() {
  const [health, setHealth] = useState(null)
  const [sandbox, setSandbox] = useState(null)
  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ ok: false }))
    api.sandbox().then(setSandbox).catch(() => setSandbox({ ready: false }))
  }, [])
  return (
    <div className="system-status">
      <span className={`dot ${health?.key_configured ? 'on' : health ? 'off' : ''}`} />
      <span>{health?.model ?? 'API…'}</span>
      <span className={`dot ${sandbox?.ready ? 'on' : sandbox ? 'off' : ''}`} />
      <span>{sandbox ? (sandbox.ready ? 'Sandbox ready' : 'Sandbox offline') : 'Sandbox…'}</span>
    </div>
  )
}

export default function App() {
  const route = useHashRoute()
  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#/">
          <span className="brand-mark">RP</span>
          <span>
            RunbookPilot
            <small>Runbooks in, tested automation out</small>
          </span>
        </a>
        <SystemStatus />
      </header>
      <main className="content">
        {route.page === 'detail' ? <RunbookDetail id={route.id} /> : <RunbookList />}
      </main>
    </div>
  )
}
