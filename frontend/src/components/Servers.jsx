import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { useSession } from '../session.jsx'
import { timeAgo } from './common.jsx'

function useLoad(fn) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const load = () => fn().then(setData).catch((e) => setError(e.message))
  useEffect(() => {
    load()
  }, [])
  return [data, load, error]
}

function CredentialForm({ onSaved }) {
  const empty = { name: '', kind: 'ssh_key', username: '', secret: '', passphrase: '' }
  const [form, setForm] = useState(empty)
  const [error, setError] = useState(null)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  async function submit(e) {
    e.preventDefault()
    setError(null)
    try {
      await api.createCredential({ ...form, passphrase: form.passphrase || null })
      setForm(empty)
      onSaved()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <form className="stack-sm" onSubmit={submit}>
      <h3>Add a credential</h3>
      <div className="form-grid">
        <input placeholder="Name, e.g. contoso-ops-key" value={form.name} onChange={set('name')} />
        <select value={form.kind} onChange={set('kind')}>
          <option value="ssh_key">SSH private key</option>
          <option value="password">Password</option>
        </select>
        <input placeholder="SSH username" value={form.username} onChange={set('username')} autoComplete="off" />
      </div>
      {form.kind === 'ssh_key' ? (
        <>
          <textarea
            rows={4}
            className="mono small"
            placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"
            value={form.secret}
            onChange={set('secret')}
            spellCheck={false}
          />
          <input type="password" placeholder="Key passphrase (if any)" value={form.passphrase} onChange={set('passphrase')} autoComplete="new-password" />
        </>
      ) : (
        <input type="password" placeholder="Password" value={form.secret} onChange={set('secret')} autoComplete="new-password" />
      )}
      <p className="muted small">Encrypted before it's stored and never shown again, not even to admins.</p>
      <div className="actions">
        {error && <span className="error-text">{error}</span>}
        <button className="btn btn-primary" disabled={!form.name || !form.username || !form.secret}>
          Save credential
        </button>
      </div>
    </form>
  )
}

function ServerForm({ credentials, onSaved }) {
  const empty = { name: '', hostname: '', port: 22, group_name: '', credential_id: '' }
  const [form, setForm] = useState(empty)
  const [error, setError] = useState(null)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  async function submit(e) {
    e.preventDefault()
    setError(null)
    try {
      await api.createServer({
        ...form,
        port: Number(form.port) || 22,
        group_name: form.group_name || null,
        credential_id: form.credential_id ? Number(form.credential_id) : null,
      })
      setForm(empty)
      onSaved()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <form className="stack-sm" onSubmit={submit}>
      <h2>Add a server</h2>
      <div className="form-grid">
        <input placeholder="Name, e.g. contoso-web-01" value={form.name} onChange={set('name')} />
        <input placeholder="Hostname or IP" value={form.hostname} onChange={set('hostname')} />
        <input placeholder="Port" type="number" value={form.port} onChange={set('port')} />
        <input placeholder="Group (client or environment)" value={form.group_name} onChange={set('group_name')} />
        <select value={form.credential_id} onChange={set('credential_id')}>
          <option value="">Credential…</option>
          {credentials?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} ({c.username})
            </option>
          ))}
        </select>
      </div>
      <div className="actions">
        {error && <span className="error-text">{error}</span>}
        <button className="btn btn-primary" disabled={!form.name || !form.hostname}>
          Add server
        </button>
      </div>
    </form>
  )
}

export function ServersPage() {
  const { can } = useSession()
  const admin = can('admin')
  const [servers, loadServers, serversError] = useLoad(api.servers)
  const [credentials, loadCredentials] = useLoad(api.credentials)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)

  async function action(id, fn) {
    setBusy(id)
    setError(null)
    try {
      await fn()
      loadServers()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(null)
    }
  }

  const groups = {}
  for (const sv of servers ?? []) (groups[sv.group_name || 'Ungrouped'] ??= []).push(sv)

  return (
    <div className="stack">
      <div>
        <h1>Servers</h1>
        <p className="muted">
          Where approved scripts run. Each server's identity (SSH host key) is pinned on its first successful test; after
          that, a server presenting a different key is refused.
        </p>
      </div>
      {(error || serversError) && <div className="panel error-text">{error || serversError}</div>}

      <section className="panel">
        {servers?.length === 0 && <div className="empty">No servers yet.{admin ? ' Add one below.' : ''}</div>}
        {Object.entries(groups).map(([group, list]) => (
          <div key={group} className="server-group">
            <h3>{group}</h3>
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>Server</th>
                    <th>Credential</th>
                    <th>Identity</th>
                    <th>Last check</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {list.map((sv) => (
                    <tr key={sv.id} className="no-hover">
                      <td>
                        <div className="strong">
                          {sv.name} {!sv.enabled && <span className="tag">disabled</span>}
                        </div>
                        <div className="muted small mono">
                          {sv.username ? `${sv.username}@` : ''}
                          {sv.hostname}:{sv.port}
                        </div>
                      </td>
                      <td className="small">{sv.credential_name ?? <span className="error-text">none</span>}</td>
                      <td className="small">
                        {sv.verified ? (
                          <span className="chip chip-good" title={sv.host_key_fingerprint}>
                            Verified
                          </span>
                        ) : (
                          <span className="chip chip-attention">Not verified</span>
                        )}
                        {sv.host_key_fingerprint && <div className="muted mono tiny">{sv.host_key_fingerprint}</div>}
                      </td>
                      <td className="small">
                        {sv.last_check_at ? (
                          <>
                            <span className={sv.last_check_ok ? 'ok-text' : 'error-text'}>{sv.last_check_ok ? 'OK' : 'Failed'}</span>{' '}
                            <span className="muted">{timeAgo(sv.last_check_at)}</span>
                            <div className="muted tiny">{sv.last_check_detail}</div>
                          </>
                        ) : (
                          <span className="muted">never</span>
                        )}
                      </td>
                      <td className="nowrap">
                        {admin && (
                          <>
                            <button className="btn btn-ghost btn-small" disabled={busy === sv.id} onClick={() => action(sv.id, () => api.testServer(sv.id))}>
                              {busy === sv.id ? 'Testing…' : 'Test connection'}
                            </button>{' '}
                            {sv.verified && (
                              <button
                                className="btn btn-ghost btn-small"
                                onClick={() =>
                                  window.confirm(`Forget ${sv.name}'s pinned identity? Only do this if the server was rebuilt.`) &&
                                  action(sv.id, () => api.updateServer(sv.id, { reset_host_key: true }))
                                }
                              >
                                Reset identity
                              </button>
                            )}{' '}
                            <button
                              className="btn btn-ghost btn-small"
                              onClick={() => action(sv.id, () => api.updateServer(sv.id, { enabled: !sv.enabled }))}
                            >
                              {sv.enabled ? 'Disable' : 'Enable'}
                            </button>{' '}
                            <button
                              className="btn btn-ghost btn-small"
                              onClick={() => window.confirm(`Delete ${sv.name}?`) && action(sv.id, () => api.deleteServer(sv.id))}
                            >
                              Delete
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </section>

      {admin && (
        <div className="two-col">
          <section className="panel">
            <ServerForm credentials={credentials} onSaved={loadServers} />
          </section>
          <section className="panel stack-sm">
            <h2>Credentials</h2>
            {credentials?.length === 0 && <p className="muted small">None yet.</p>}
            <ul className="cred-list">
              {credentials?.map((c) => (
                <li key={c.id}>
                  <span>
                    <strong>{c.name}</strong> <span className="muted small">{c.kind === 'ssh_key' ? 'SSH key' : 'password'} · {c.username}</span>
                    {c.public_fingerprint && <div className="muted mono tiny">{c.public_fingerprint}</div>}
                  </span>
                  <button
                    className="btn btn-ghost btn-small"
                    onClick={() =>
                      window.confirm(`Delete credential ${c.name}?`) &&
                      api.deleteCredential(c.id).then(loadCredentials).catch((e) => setError(e.message))
                    }
                  >
                    Delete
                  </button>
                </li>
              ))}
            </ul>
            <CredentialForm onSaved={loadCredentials} />
          </section>
        </div>
      )}
    </div>
  )
}
