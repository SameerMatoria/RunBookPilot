import { useCallback, useEffect, useRef, useState } from 'react'
import { api, BUSY } from '../api.js'
import { clockTime, RiskBadge, StatusChip } from './common.jsx'
import { ApprovalPanel, FailurePanel, QuestionsPanel, ReviewCard } from './Panels.jsx'
import StepReview from './StepReview.jsx'

const STAGES = ['Upload', 'Parse', 'Questions', 'Script', 'Sandbox test', 'Review', 'Approve']

// Map the runbook status onto the 7-stage pipeline: which stage we're at and its state.
function pipelineState(record) {
  const hadQuestions = (record.parsed?.steps ?? []).some((s) => s.ambiguous)
  const at = {
    uploaded: [1, 'active'],
    parsing: [1, 'active'],
    needs_answers: [2, 'attention'],
    parsed: [3, 'active'],
    writing_script: [3, 'active'],
    testing: [4, 'active'],
    tests_failed: [4, 'failed'],
    reviewing: [5, 'active'],
    awaiting_approval: [6, 'attention'],
    rejected: [6, 'failed'],
    approved: [7, 'done'],
  }[record.status]
  if (at) return { index: at[0], state: at[1], hadQuestions }
  // error: fail at the stage we got to
  const index = !record.parsed ? 1 : !record.scripts?.length ? 3 : record.review ? 6 : 4
  return { index, state: 'failed', hadQuestions }
}

function Pipeline({ record }) {
  const { index, state, hadQuestions } = pipelineState(record)
  return (
    <ol className="pipeline">
      {STAGES.map((name, i) => {
        let cls = i < index ? 'done' : i === index ? state : 'todo'
        if (name === 'Questions' && i < index && !hadQuestions) cls = 'skipped'
        return (
          <li key={name} className={`stage stage-${cls}`}>
            <span className="stage-dot">
              {cls === 'done' ? '✓' : cls === 'failed' ? '!' : cls === 'skipped' ? '–' : i + 1}
            </span>
            <span className="stage-name">{name}</span>
          </li>
        )
      })}
    </ol>
  )
}

function ActivityLog({ events, busy }) {
  const end = useRef(null)
  useEffect(() => {
    end.current?.scrollIntoView({ block: 'nearest' })
  }, [events.length])
  return (
    <div className="panel activity">
      <div className="panel-head">
        <h2>Agent activity</h2>
        {busy && (
          <span className="live">
            <span className="pulse" /> live
          </span>
        )}
      </div>
      <ul className="events">
        {events.map((e, i) => (
          <li key={i} className={`event ev-${e.level}`}>
            <span className="ev-time">{clockTime(e.at)}</span>
            <span className={`agent agent-${e.agent.toLowerCase()}`}>{e.agent}</span>
            <span className="ev-msg">{e.message}</span>
          </li>
        ))}
        {busy && (
          <li className="event ev-pending">
            <span className="ev-time" />
            <span className="spinner" />
            <span className="ev-msg muted">working…</span>
          </li>
        )}
        <li ref={end} />
      </ul>
    </div>
  )
}

export default function RunbookDetail({ id }) {
  const [record, setRecord] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(
    () =>
      api
        .get(id)
        .then((r) => {
          setRecord(r)
          setError(null)
          return r
        })
        .catch((e) => setError(e.message)),
    [id],
  )

  // Poll while agents are working; stop once they're done.
  useEffect(() => {
    let timer
    let cancelled = false
    const tick = async () => {
      const r = await load()
      if (!cancelled && r && BUSY.has(r.status)) timer = setTimeout(tick, 1200)
    }
    tick()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [load, record?.status])

  // Actions update the record, then polling picks up from the new status.
  const act = useCallback(async (promise) => {
    const r = await promise
    setRecord(r)
    return r
  }, [])

  if (error && !record) return <div className="panel error-text">{error}</div>
  if (!record) return <div className="panel muted">Loading…</div>

  const busy = BUSY.has(record.status)
  const parsed = record.parsed

  async function remove() {
    if (!window.confirm('Delete this runbook and all its scripts and test results?')) return
    await api.remove(record.id)
    window.location.hash = '#/'
  }

  return (
    <div className="stack">
      <div className="detail-head">
        <div>
          <a href="#/" className="back">
            ← All runbooks
          </a>
          <h1>{parsed?.title ?? record.source_file}</h1>
          <div className="meta">
            <StatusChip status={record.status} />
            <RiskBadge tier={parsed?.risk_tier} />
            {parsed?.target_os && <span className="tag">{parsed.target_os}</span>}
            <span className="muted small">{record.source_file}</span>
          </div>
          {parsed?.risk_reason && <p className="muted small risk-reason">{parsed.risk_reason}</p>}
        </div>
        <button className="btn btn-ghost btn-small" onClick={remove} disabled={busy}>
          Delete
        </button>
      </div>

      <Pipeline record={record} />

      <div className="detail-grid">
        <div className="stack">
          {record.status === 'needs_answers' && <QuestionsPanel record={record} act={act} />}
          {record.status === 'error' && <FailurePanel record={record} act={act} kind="error" />}
          {record.status === 'tests_failed' && <FailurePanel record={record} act={act} kind="tests" />}
          {record.review && !busy && (
            <>
              <ReviewCard record={record} />
              <ApprovalPanel record={record} act={act} />
            </>
          )}
          {parsed && <StepReview record={record} />}
        </div>
        <ActivityLog events={record.events ?? []} busy={busy} />
      </div>
    </div>
  )
}
