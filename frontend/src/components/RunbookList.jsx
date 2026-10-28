import { useEffect, useRef, useState } from 'react'
import { api, BUSY } from '../api.js'
import { RiskBadge, StatusChip, timeAgo } from './common.jsx'
import { useSession } from '../session.jsx'

function UploadZone() {
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState(null)
  const [uploading, setUploading] = useState(false)
  const input = useRef(null)

  async function upload(file) {
    if (!file) return
    setError(null)
    setUploading(true)
    try {
      const record = await api.upload(file)
      window.location.hash = `#/runbooks/${record.id}`
    } catch (e) {
      setError(e.message)
      setUploading(false)
    }
  }

  return (
    <div
      className={`upload ${dragging ? 'dragging' : ''}`}
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        upload(e.dataTransfer.files[0])
      }}
      onClick={() => input.current?.click()}
    >
      <input
        ref={input}
        type="file"
        accept=".pdf,.docx,.md,.txt"
        hidden
        onChange={(e) => upload(e.target.files[0])}
      />
      <div className="upload-icon">⇪</div>
      <div className="upload-title">{uploading ? 'Uploading…' : 'Drop a runbook here'}</div>
      <div className="muted">PDF, Word, Markdown or text · or click to choose a file</div>
      {error && <div className="error-text">{error}</div>}
    </div>
  )
}

export default function RunbookList() {
  const { can } = useSession()
  const [runbooks, setRunbooks] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let timer
    const load = () =>
      api
        .list()
        .then((rows) => {
          setRunbooks(rows)
          setError(null)
          // Keep refreshing while any runbook is still being worked on.
          if (rows.some((r) => BUSY.has(r.status))) timer = setTimeout(load, 2000)
        })
        .catch((e) => setError(e.message))
    load()
    return () => clearTimeout(timer)
  }, [])

  const approved = runbooks?.filter((r) => r.status === 'approved').length ?? 0

  return (
    <div className="stack">
      <section className="hero">
        <div>
          <h1>Turn a runbook into tested automation</h1>
          <p className="muted">
            Upload a runbook. Agents pull out the steps, write a script, test it in a disposable sandbox and
            hand it to you for approval. Nothing runs for real until an engineer approves it.
          </p>
        </div>
        {can('submitter') ? (
          <UploadZone />
        ) : (
          <div className="upload muted">You can view runbooks. Uploading needs the submitter role.</div>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Runbooks</h2>
          {runbooks && (
            <span className="muted">
              {runbooks.length} total · {approved} in automation library
            </span>
          )}
        </div>
        {error && <div className="error-text">Can't reach the backend: {error}</div>}
        {runbooks?.length === 0 && <div className="empty">No runbooks yet. Upload one to get started.</div>}
        {runbooks?.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Runbook</th>
                <th>Risk</th>
                <th>Steps</th>
                <th>Script</th>
                <th>Status</th>
                <th>Uploaded</th>
              </tr>
            </thead>
            <tbody>
              {runbooks.map((r) => (
                <tr key={r.id} onClick={() => (window.location.hash = `#/runbooks/${r.id}`)}>
                  <td>
                    <div className="strong">{r.title}</div>
                    <div className="muted small">{r.source_file}</div>
                  </td>
                  <td>
                    <RiskBadge tier={r.risk_tier} />
                  </td>
                  <td>{r.steps || '–'}</td>
                  <td>{r.script_versions ? `v${r.script_versions}` : '–'}</td>
                  <td>
                    <StatusChip status={r.status} />
                  </td>
                  <td className="muted">{timeAgo(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
