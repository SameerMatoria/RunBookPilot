import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { useSession } from '../session.jsx'
import { StepBadge, timeAgo } from './common.jsx'

const RUN_TONE = { queued: 'busy', running: 'busy', cancelling: 'busy', succeeded: 'good', failed: 'bad', cancelled: 'neutral' }
const ACTIVE = new Set(['queued', 'running', 'cancelling'])
const TRIGGER_LABEL = { manual: 'by hand', schedule: 'scheduled', alert: 'alert' }

export function RunStatus({ status }) {
  return (
    <span className={`chip chip-${RUN_TONE[status] ?? 'neutral'}`}>
      {ACTIVE.has(status) && <span className="spinner" />}
      {status}
    </span>
  )
}

export function RunsTable({ runs, showRunbook = true }) {
  if (!runs?.length) return <div className="empty">No runs yet.</div>
  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th>#</th>
            {showRunbook && <th>Runbook</th>}
            <th>Server</th>
            <th>Mode</th>
            <th>Status</th>
            <th>Started by</th>
            <th className="num">Took</th>
            <th>When</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id} onClick={() => (window.location.hash = `#/runs/${r.id}`)}>
              <td className="muted">{r.id}</td>
              {showRunbook && <td className="strong">{r.runbook_title}</td>}
              <td className="mono small">{r.server_name}</td>
              <td>
                <span className="tag">{r.mode === 'execute' ? 'execute' : 'dry run'}</span>
              </td>
              <td>
                <RunStatus status={r.status} />
              </td>
              <td className="small">
                {r.requested_by_name} <span className="muted">({TRIGGER_LABEL[r.trigger] ?? r.trigger})</span>
                {r.ticket && <div className="muted tiny">ticket {r.ticket}</div>}
              </td>
              <td className="num">{r.duration_s != null ? `${r.duration_s.toFixed(1)} s` : '–'}</td>
              <td className="muted small">{timeAgo(r.queued_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function RunsPage() {
  const [runs, setRuns] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let timer
    const load = () =>
      api
        .runs({ limit: 200 })
        .then((rows) => {
          setRuns(rows)
          if (rows.some((r) => ACTIVE.has(r.status))) timer = setTimeout(load, 2000)
        })
        .catch((e) => setError(e.message))
    load()
    return () => clearTimeout(timer)
  }, [])

  return (
    <div className="stack">
      <div>
        <h1>Runs</h1>
        <p className="muted">Every time an approved script ran on a server: who or what started it, what happened, and the full output.</p>
      </div>
      {error && <div className="panel error-text">{error}</div>}
      <section className="panel">
        <RunsTable runs={runs} />
      </section>
    </div>
  )
}

export function RunDetail({ id }) {
  const { can } = useSession()
  const [run, setRun] = useState(null)
  const [error, setError] = useState(null)
  const output = useRef(null)

  useEffect(() => {
    let timer
    let cancelled = false
    const load = () =>
      api
        .run(id)
        .then((r) => {
          if (cancelled) return
          setRun(r)
          if (ACTIVE.has(r.status)) timer = setTimeout(load, 1000)
        })
        .catch((e) => setError(e.message))
    load()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [id])

  useEffect(() => {
    const box = output.current
    if (box && run && ACTIVE.has(run.status)) box.scrollTop = box.scrollHeight
  }, [run?.output?.length])

  if (error) return <div className="panel error-text">{error}</div>
  if (!run) return <div className="panel muted">Loading…</div>

  const stepNames = Object.fromEntries((run.parsed_steps ?? []).map((s) => [s.order, s.action]))

  return (
    <div className="stack">
      <div className="detail-head">
        <div>
          <a href="#/runs" className="back">
            ← All runs
          </a>
          <h1>
            Run #{run.id}: {run.runbook_title}
          </h1>
          <div className="meta">
            <RunStatus status={run.status} />
            <span className="tag">{run.mode === 'execute' ? 'execute' : 'dry run'}</span>
            <span className="mono small">{run.server_name}</span>
            <span className="muted small">
              script v{run.script_version} · started by {run.requested_by_name} ({TRIGGER_LABEL[run.trigger] ?? run.trigger})
              {run.ticket && ` · ticket ${run.ticket}`}
            </span>
          </div>
          <p className="muted tiny mono">sha256 {run.script_sha256}</p>
        </div>
        {can('operator') && ACTIVE.has(run.status) && run.status !== 'cancelling' && (
          <button className="btn btn-danger btn-small" onClick={() => api.cancelRun(run.id).then(() => setRun({ ...run, status: 'cancelling' }))}>
            Cancel
          </button>
        )}
      </div>

      {run.error && <div className="panel panel-bad">{run.error}</div>}

      <div className="run-grid">
        <section className="panel">
          <div className="panel-head">
            <h2>Steps</h2>
            {run.duration_s != null && <span className="muted small">{run.duration_s.toFixed(1)} s</span>}
          </div>
          {run.steps.length === 0 && <div className="muted small">{ACTIVE.has(run.status) ? 'Waiting for output…' : 'No step results.'}</div>}
          <ul className="run-steps">
            {run.steps.map((s) => (
              <li key={s.order}>
                <StepBadge label={`Step ${s.order}`} status={s.status} />
                <span className="small">{stepNames[s.order] ?? ''}</span>
                <span className="muted tiny">{s.messages?.at(-1)}</span>
              </li>
            ))}
          </ul>
          <p className="muted small">
            <a href={`#/runbooks/${run.runbook_id}`}>Open the runbook →</a>
          </p>
        </section>
        <section className="panel">
          <div className="panel-head">
            <h2>Output</h2>
            {ACTIVE.has(run.status) && (
              <span className="live">
                <span className="pulse" /> live
              </span>
            )}
          </div>
          <pre className="console tall" ref={output}>
            {run.output || '(no output yet)'}
          </pre>
        </section>
      </div>
    </div>
  )
}
