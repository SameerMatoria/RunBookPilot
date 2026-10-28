import { Fragment, useEffect, useState } from 'react'
import { api, ROLES } from '../api.js'
import { useSession } from '../session.jsx'
import { timeAgo } from './common.jsx'

const ROLE_HELP = {
  submitter: 'uploads runbooks and answers questions',
  approver: 'approves or rejects scripts',
  operator: 'runs approved scripts on servers',
  admin: 'everything, plus users and servers',
}

function NewUserForm({ onCreated }) {
  const empty = { username: '', display_name: '', password: '', roles: ['submitter'] }
  const [form, setForm] = useState(empty)
  const [error, setError] = useState(null)

  async function submit(e) {
    e.preventDefault()
    setError(null)
    try {
      await api.createUser(form)
      setForm(empty)
      onCreated()
    } catch (err) {
      setError(err.message)
    }
  }

  const toggle = (role) =>
    setForm({ ...form, roles: form.roles.includes(role) ? form.roles.filter((r) => r !== role) : [...form.roles, role] })

  return (
    <form className="panel stack-sm" onSubmit={submit}>
      <h2>Add a local user</h2>
      <p className="muted small">People with Microsoft accounts don't need this: they appear here after their first sign-in.</p>
      <div className="form-grid">
        <input placeholder="Username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
        <input placeholder="Display name" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
        <input
          type="password"
          placeholder="Temporary password (8+ characters)"
          autoComplete="new-password"
          value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })}
        />
      </div>
      <div className="role-picks">
        {ROLES.map((r) => (
          <label key={r} className="check" title={ROLE_HELP[r]}>
            <input type="checkbox" checked={form.roles.includes(r)} onChange={() => toggle(r)} /> {r}
          </label>
        ))}
      </div>
      <div className="actions">
        {error && <span className="error-text">{error}</span>}
        <button className="btn btn-primary" disabled={!form.username || !form.password}>
          Add user
        </button>
      </div>
    </form>
  )
}

export function UsersPage() {
  const { user: me } = useSession()
  const [users, setUsers] = useState(null)
  const [error, setError] = useState(null)

  const load = () => api.users().then(setUsers).catch((e) => setError(e.message))
  useEffect(() => {
    load()
  }, [])

  async function change(u, data) {
    setError(null)
    try {
      await api.updateUser(u.id, data)
      load()
    } catch (e) {
      setError(e.message)
    }
  }

  async function resetPassword(u) {
    const password = window.prompt(`New password for ${u.username} (at least 8 characters):`)
    if (password) change(u, { password })
  }

  return (
    <div className="stack">
      <div>
        <h1>Users</h1>
        <p className="muted">
          Roles: {ROLES.map((r) => `${r} (${ROLE_HELP[r]})`).join(' · ')}. Nobody can approve a runbook they uploaded.
        </p>
      </div>
      {error && <div className="panel error-text">{error}</div>}
      <section className="panel">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>User</th>
                <th>Sign-in</th>
                {ROLES.map((r) => (
                  <th key={r} className="center">
                    {r}
                  </th>
                ))}
                <th>Active</th>
                <th>Last sign-in</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {users?.map((u) => (
                <tr key={u.id} className="no-hover">
                  <td>
                    <div className="strong">{u.display_name}</div>
                    <div className="muted small">{u.username}</div>
                  </td>
                  <td>
                    <span className="tag">{u.auth_provider === 'entra' ? 'Microsoft' : 'local'}</span>
                  </td>
                  {ROLES.map((r) => (
                    <td key={r} className="center">
                      <input
                        type="checkbox"
                        aria-label={`${u.username} ${r}`}
                        checked={u.roles.includes(r)}
                        onChange={() =>
                          change(u, { roles: u.roles.includes(r) ? u.roles.filter((x) => x !== r) : [...u.roles, r] })
                        }
                      />
                    </td>
                  ))}
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`${u.username} active`}
                      checked={u.active}
                      disabled={u.id === me.id}
                      onChange={() => change(u, { active: !u.active })}
                    />
                  </td>
                  <td className="muted small">{u.last_login_at ? timeAgo(u.last_login_at) : 'never'}</td>
                  <td>
                    {u.auth_provider === 'local' && (
                      <button className="btn btn-ghost btn-small" onClick={() => resetPassword(u)}>
                        Reset password
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <NewUserForm onCreated={load} />
    </div>
  )
}

const ACTION_FILTERS = [
  ['', 'Everything'],
  ['auth', 'Sign-ins'],
  ['runbook', 'Runbooks'],
  ['run', 'Script runs'],
  ['server', 'Servers & credentials'],
  ['user', 'Users'],
]

export function AuditPage() {
  const [rows, setRows] = useState([])
  const [filters, setFilters] = useState({ action: '', username: '' })
  const [more, setMore] = useState(false)
  const [open, setOpen] = useState(null)
  const [error, setError] = useState(null)

  async function load(beforeId) {
    try {
      const page = await api.audit({ ...filters, limit: 100, before_id: beforeId })
      setRows((prev) => (beforeId ? [...prev, ...page] : page))
      setMore(page.length === 100)
    } catch (e) {
      setError(e.message)
    }
  }

  useEffect(() => {
    load()
  }, [filters])

  return (
    <div className="stack">
      <div>
        <h1>Audit log</h1>
        <p className="muted">Every sign-in, upload, approval, run and change, with who did it and from where.</p>
      </div>
      <div className="filters">
        <select value={filters.action} onChange={(e) => setFilters({ ...filters, action: e.target.value })}>
          {ACTION_FILTERS.map(([v, label]) => (
            <option key={v} value={v}>
              {label}
            </option>
          ))}
        </select>
        <input
          placeholder="Filter by username"
          value={filters.username}
          onChange={(e) => setFilters({ ...filters, username: e.target.value })}
        />
      </div>
      {error && <div className="panel error-text">{error}</div>}
      <section className="panel">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>Action</th>
                <th>Target</th>
                <th>From</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <Fragment key={a.id}>
                  <tr onClick={() => setOpen(open === a.id ? null : a.id)}>
                    <td className="nowrap" title={a.at}>
                      {new Date(a.at).toLocaleString()}
                    </td>
                    <td>{a.username ?? <span className="muted">anonymous</span>}</td>
                    <td>
                      <code className="inline-cmd">{a.action}</code>
                    </td>
                    <td className="small">
                      {a.target_type === 'runbook' ? (
                        <a href={`#/runbooks/${a.target_id}`} onClick={(e) => e.stopPropagation()}>
                          runbook {a.target_id}
                        </a>
                      ) : a.target_type ? (
                        `${a.target_type} ${a.target_id ?? ''}`
                      ) : (
                        '–'
                      )}
                    </td>
                    <td className="muted small">{a.ip ?? '–'}</td>
                  </tr>
                  {open === a.id && (
                    <tr className="no-hover">
                      <td colSpan={5}>
                        <pre className="console">{JSON.stringify(a.details, null, 2)}</pre>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length === 0 && <div className="empty">Nothing recorded yet.</div>}
        {more && (
          <div className="actions">
            <button className="btn btn-ghost" onClick={() => load(rows.at(-1).id)}>
              Load older
            </button>
          </div>
        )}
      </section>
    </div>
  )
}
