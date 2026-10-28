import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { useSession } from '../session.jsx'
import { RunsTable } from './Runs.jsx'

const CRON_PRESETS = [
  ['0 2 * * *', 'Every day at 02:00 UTC'],
  ['0 * * * *', 'Every hour'],
  ['*/15 * * * *', 'Every 15 minutes'],
  ['0 6 * * 1', 'Mondays at 06:00 UTC'],
]

function ServerPicker({ servers, selected, onChange }) {
  const usable = (servers ?? []).filter((s) => s.enabled && s.verified && s.credential_id)
  if (!servers) return <span className="muted small">Loading servers…</span>
  if (!usable.length)
    return (
      <span className="muted small">
        No verified servers yet. <a href="#/servers">Add and test one</a> first.
      </span>
    )
  const toggle = (id) => onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id])
  return (
    <div className="server-picks">
      {usable.map((s) => (
        <label key={s.id} className="check">
          <input type="checkbox" checked={selected.includes(s.id)} onChange={() => toggle(s.id)} />
          <span className="mono small">{s.name}</span>
          {s.group_name && <span className="muted tiny">{s.group_name}</span>}
        </label>
      ))}
    </div>
  )
}

export default function RunPanel({ record }) {
  const { can } = useSession()
  const operator = can('operator')
  const highRisk = record.parsed?.risk_tier === 'high'
  const [tab, setTab] = useState('run')
  const [servers, setServers] = useState(null)
  const [runs, setRuns] = useState(null)
  const [schedules, setSchedules] = useState([])
  const [triggers, setTriggers] = useState([])
  const [form, setForm] = useState({ server_ids: [], mode: 'dry_run', ticket: '' })
  const [schedForm, setSchedForm] = useState({ name: '', cron: CRON_PRESETS[0][0], mode: 'execute' })
  const [trigForm, setTrigForm] = useState({ name: '', mode: highRisk ? 'dry_run' : 'execute', cooldown_minutes: 5 })
  const [newToken, setNewToken] = useState(null)
  const [error, setError] = useState(null)
  const [pending, setPending] = useState(false)

  const loadRuns = () => api.runs({ runbook_id: record.id, limit: 20 }).then(setRuns)
  const loadAutomation = () => {
    api.schedules(record.id).then(setSchedules)
    api.triggers(record.id).then(setTriggers)
  }

  useEffect(() => {
    if (operator) api.servers().then(setServers).catch(() => setServers([]))
    loadAutomation()
  }, [record.id])

  // Refresh the run list while any run is still going.
  useEffect(() => {
    let timer
    const tick = () =>
      api.runs({ runbook_id: record.id, limit: 20 }).then((rows) => {
        setRuns(rows)
        if (rows.some((r) => ['queued', 'running', 'cancelling'].includes(r.status))) timer = setTimeout(tick, 1500)
      })
    tick()
    return () => clearTimeout(timer)
  }, [record.id, runs?.length])

  async function attempt(fn) {
    setPending(true)
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError(e.message)
    } finally {
      setPending(false)
    }
  }

  const startRun = () =>
    attempt(async () => {
      await api.startRun(record.id, { ...form, ticket: form.ticket || null })
      loadRuns()
    })

  const addSchedule = () =>
    attempt(async () => {
      await api.createSchedule(record.id, { ...schedForm, server_ids: form.server_ids, ticket: form.ticket || null })
      setSchedForm({ ...schedForm, name: '' })
      loadAutomation()
    })

  const addTrigger = () =>
    attempt(async () => {
      const created = await api.createTrigger(record.id, { ...trigForm, server_ids: form.server_ids })
      setNewToken(created)
      setTrigForm({ ...trigForm, name: '' })
      loadAutomation()
    })

  const webhookUrl = (t) => `${window.location.origin}/api${t.url_path}`

  return (
    <section className="panel">
      <div className="panel-head tabs-head">
        <div className="tabs">
          <button className={tab === 'run' ? 'active' : ''} onClick={() => setTab('run')}>
            Run on servers
          </button>
          <button className={tab === 'schedule' ? 'active' : ''} onClick={() => setTab('schedule')}>
            Schedules {schedules.length ? `(${schedules.length})` : ''}
          </button>
          <button className={tab === 'alerts' ? 'active' : ''} onClick={() => setTab('alerts')}>
            Alert triggers {triggers.length ? `(${triggers.length})` : ''}
          </button>
        </div>
      </div>

      {operator && (
        <div className="stack-sm run-form">
          <div>
            <h3>Servers</h3>
            <ServerPicker servers={servers} selected={form.server_ids} onChange={(ids) => setForm({ ...form, server_ids: ids })} />
          </div>
          {tab === 'run' && (
            <div className="form-row">
              <label className="check">
                <input type="radio" checked={form.mode === 'dry_run'} onChange={() => setForm({ ...form, mode: 'dry_run' })} /> Dry run only
                <span className="muted tiny">shows what it would change</span>
              </label>
              <label className="check">
                <input type="radio" checked={form.mode === 'execute'} onChange={() => setForm({ ...form, mode: 'execute' })} /> Execute
                <span className="muted tiny">dry run first, then for real</span>
              </label>
              <input
                className="ticket"
                placeholder={highRisk ? 'Change ticket (required)' : 'Change ticket (optional)'}
                value={form.ticket}
                onChange={(e) => setForm({ ...form, ticket: e.target.value })}
              />
              <button
                className={`btn ${form.mode === 'execute' ? 'btn-danger-solid' : 'btn-primary'}`}
                disabled={pending || !form.server_ids.length || (highRisk && form.mode === 'execute' && !form.ticket.trim())}
                onClick={() =>
                  form.mode === 'execute'
                    ? window.confirm(`Execute v${record.approved_version} on ${form.server_ids.length} server(s)? This makes real changes.`) && startRun()
                    : startRun()
                }
              >
                {form.mode === 'execute' ? 'Execute now' : 'Start dry run'}
              </button>
            </div>
          )}
          {tab === 'schedule' && (
            <div className="form-row">
              <input placeholder="Schedule name" value={schedForm.name} onChange={(e) => setSchedForm({ ...schedForm, name: e.target.value })} />
              <select value={schedForm.cron} onChange={(e) => setSchedForm({ ...schedForm, cron: e.target.value })}>
                {CRON_PRESETS.map(([c, label]) => (
                  <option key={c} value={c}>
                    {label}
                  </option>
                ))}
              </select>
              <input className="mono cron" value={schedForm.cron} onChange={(e) => setSchedForm({ ...schedForm, cron: e.target.value })} title="cron, UTC" />
              <select value={schedForm.mode} onChange={(e) => setSchedForm({ ...schedForm, mode: e.target.value })}>
                <option value="execute">execute</option>
                <option value="dry_run">dry run</option>
              </select>
              <button className="btn btn-primary" disabled={pending || !schedForm.name || !form.server_ids.length} onClick={addSchedule}>
                Add schedule
              </button>
            </div>
          )}
          {tab === 'alerts' && (
            <div className="form-row">
              <input placeholder="Trigger name, e.g. 'disk full alert'" value={trigForm.name} onChange={(e) => setTrigForm({ ...trigForm, name: e.target.value })} />
              <select value={trigForm.mode} onChange={(e) => setTrigForm({ ...trigForm, mode: e.target.value })}>
                {!highRisk && <option value="execute">execute</option>}
                <option value="dry_run">dry run</option>
              </select>
              <label className="small">
                cooldown{' '}
                <input
                  type="number"
                  className="narrow"
                  value={trigForm.cooldown_minutes}
                  onChange={(e) => setTrigForm({ ...trigForm, cooldown_minutes: Number(e.target.value) })}
                />{' '}
                min
              </label>
              <button className="btn btn-primary" disabled={pending || !trigForm.name || !form.server_ids.length} onClick={addTrigger}>
                Create webhook
              </button>
            </div>
          )}
          {error && <div className="error-text">{error}</div>}
        </div>
      )}
      {!operator && <p className="muted small">Running scripts on servers needs the operator role.</p>}

      {tab === 'run' && (
        <>
          <h3>Recent runs</h3>
          <RunsTable runs={runs} showRunbook={false} />
        </>
      )}

      {tab === 'schedule' && (
        <ul className="auto-list">
          {schedules.length === 0 && <li className="muted small">No schedules. Times are in UTC.</li>}
          {schedules.map((s) => (
            <li key={s.id}>
              <div>
                <strong>{s.name}</strong> <code className="inline-cmd">{s.cron}</code> <span className="tag">{s.mode === 'execute' ? 'execute' : 'dry run'}</span>
                <div className="muted tiny">
                  {s.enabled ? `next: ${new Date(s.next_run_at).toLocaleString()}` : 'paused'}
                  {s.last_run_at && ` · last: ${new Date(s.last_run_at).toLocaleString()}`} · {s.server_ids.length} server(s)
                </div>
              </div>
              {operator && (
                <span className="nowrap">
                  <button className="btn btn-ghost btn-small" onClick={() => api.updateSchedule(s.id, { enabled: !s.enabled }).then(loadAutomation)}>
                    {s.enabled ? 'Pause' : 'Resume'}
                  </button>{' '}
                  <button className="btn btn-ghost btn-small" onClick={() => window.confirm('Delete this schedule?') && api.deleteSchedule(s.id).then(loadAutomation)}>
                    Delete
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      {tab === 'alerts' && (
        <>
          {newToken && (
            <div className="token-box">
              <strong>Copy this now: the token won't be shown again.</strong>
              <pre className="console">{`curl -X POST ${webhookUrl(newToken)} \\
  -H "X-RunbookPilot-Token: ${newToken.token}" \\
  -H "Content-Type: application/json" -d '{"host": "<server name or hostname>"}'`}</pre>
              <button className="btn btn-ghost btn-small" onClick={() => setNewToken(null)}>
                I've saved it
              </button>
            </div>
          )}
          <ul className="auto-list">
            {triggers.length === 0 && (
              <li className="muted small">
                No triggers. A trigger gives your monitoring tool a webhook URL that starts this script, e.g. when a "disk full"
                alert fires.{highRisk && ' High-risk scripts can only be dry-run from alerts.'}
              </li>
            )}
            {triggers.map((t) => (
              <li key={t.id}>
                <div>
                  <strong>{t.name}</strong> <span className="tag">{t.mode === 'execute' ? 'execute' : 'dry run'}</span>
                  <div className="muted tiny mono">POST {webhookUrl(t)}</div>
                  <div className="muted tiny">
                    cooldown {t.cooldown_minutes} min · {t.server_ids.length} server(s)
                    {t.last_fired_at && ` · last fired ${new Date(t.last_fired_at).toLocaleString()}`}
                  </div>
                </div>
                {operator && (
                  <button className="btn btn-ghost btn-small" onClick={() => window.confirm('Delete this trigger?') && api.deleteTrigger(t.id).then(loadAutomation)}>
                    Delete
                  </button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
