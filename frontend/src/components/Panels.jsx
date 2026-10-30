import { useState } from 'react'
import { api } from '../api.js'
import { clockTime } from './common.jsx'
import { useSession } from '../session.jsx'

function useAction() {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(null)
  const run = async (fn) => {
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
  return { pending, error, run }
}

export function QuestionsPanel({ record, act }) {
  const questions = record.parsed.steps.filter((s) => s.ambiguous && !s.answer)
  const [answers, setAnswers] = useState({})
  const { pending, error, run } = useAction()
  const complete = questions.every((q) => answers[q.order]?.trim())

  return (
    <section className="panel panel-attention">
      <div className="panel-head">
        <h2>The Parser needs your input</h2>
        <span className="muted">
          {questions.length} unclear step{questions.length === 1 ? '' : 's'}. The agent asks instead of guessing.
        </span>
      </div>
      <div className="questions">
        {questions.map((q) => (
          <label key={q.order} className="question">
            <span className="q-step">Step {q.order}</span>
            <span className="q-action">{q.action}</span>
            <span className="q-text">{q.question}</span>
            <textarea
              rows={2}
              value={answers[q.order] ?? ''}
              onChange={(e) => setAnswers({ ...answers, [q.order]: e.target.value })}
              placeholder="Your answer…"
            />
          </label>
        ))}
      </div>
      <div className="actions">
        {error && <span className="error-text">{error}</span>}
        <button
          className="btn btn-primary"
          disabled={!complete || pending}
          onClick={() => run(() => act(api.answer(record.id, answers)))}
        >
          {pending ? 'Sending…' : 'Answer and write the script'}
        </button>
      </div>
    </section>
  )
}

export function FailurePanel({ record, act, kind }) {
  const lastRun = record.test_runs?.at(-1)
  const diagnosis = kind === 'tests' ? lastRun?.diagnosis : null
  const [guidance, setGuidance] = useState('')
  const { pending, error, run } = useAction()
  const canRebuild = record.parsed?.steps?.length > 0

  return (
    <section className="panel panel-bad">
      <div className="panel-head">
        <h2>{kind === 'tests' ? 'Sandbox tests failed: handed over to you' : 'Something went wrong'}</h2>
      </div>
      {kind === 'error' && (
        <>
          <p className="mono small">{record.error}</p>
          <div className="actions">
            <span className="muted small">Retry continues from where it stopped; finished work is kept.</span>
            <button className="btn btn-primary" disabled={pending} onClick={() => run(() => act(api.retry(record.id)))}>
              Retry
            </button>
          </div>
        </>
      )}
      {diagnosis && (
        <div className="diagnosis">
          <span className="tag">{diagnosis.category?.replace('_', ' ')}</span>
          {diagnosis.failed_step && <span className="tag">step {diagnosis.failed_step}</span>}
          <p>{diagnosis.diagnosis}</p>
        </div>
      )}
      {canRebuild && kind === 'tests' && (
        <>
          <textarea
            rows={2}
            value={guidance}
            onChange={(e) => setGuidance(e.target.value)}
            placeholder="Optional: guidance for the Author agent (e.g. 'use journalctl instead of reading the log file')"
          />
          <div className="actions">
            {error && <span className="error-text">{error}</span>}
            <button className="btn btn-primary" disabled={pending} onClick={() => run(() => act(api.build(record.id, guidance)))}>
              Rewrite and retest
            </button>
          </div>
        </>
      )}
    </section>
  )
}

const RECOMMENDATION = {
  approve: ['Recommends approval', 'good'],
  approve_with_care: ['Approve with care', 'attention'],
  reject: ['Recommends rejection', 'bad'],
}

export function ReviewCard({ record }) {
  const review = record.review
  const run = record.test_runs?.at(-1)
  const [label, tone] = RECOMMENDATION[review.recommendation] ?? [review.recommendation, 'neutral']
  const executeSteps = run?.execute?.steps ?? []
  const passed = executeSteps.filter((s) => s.status === 'OK').length
  const skipped = executeSteps.filter((s) => s.status === 'SKIP').length

  return (
    <section className="panel review-card">
      <div className="panel-head">
        <h2>Reviewer summary</h2>
        <span className={`chip chip-${tone}`}>{label}</span>
      </div>
      <p className="headline">{review.headline}</p>

      <div className="evidence">
        <div>
          <span className="ev-num">{run?.passed ? 'Passed' : 'Failed'}</span>
          <span className="ev-label">sandbox tests</span>
        </div>
        <div>
          <span className="ev-num">
            {passed}/{executeSteps.length}
          </span>
          <span className="ev-label">steps passed{skipped ? `, ${skipped} skipped` : ''}</span>
        </div>
        <div>
          <span className="ev-num">{review.attempts}</span>
          <span className="ev-label">attempt{review.attempts === 1 ? '' : 's'} to pass</span>
        </div>
        <div>
          <span className="ev-num">{run?.execute?.duration_s ?? '–'}s</span>
          <span className="ev-label">run time</span>
        </div>
        <div>
          <span className="ev-num cap">{review.confidence}</span>
          <span className="ev-label">confidence</span>
        </div>
      </div>
      {review.confidence_reason && <p className="muted small">{review.confidence_reason}</p>}

      <div className="review-cols">
        <div>
          <h3>What it does</h3>
          <ol>
            {review.what_it_does?.map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ol>
          {review.changes?.length > 0 && (
            <>
              <h3>Changes it makes (with --execute)</h3>
              <ul>
                {review.changes.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </>
          )}
        </div>
        <div>
          <h3>Risks</h3>
          <ul className="risks">
            {review.risks?.map((r, i) => (
              <li key={i}>
                <strong>{r.risk}</strong>
                <span className="muted"> → {r.mitigation}</span>
              </li>
            ))}
          </ul>
          {review.untested?.length > 0 && (
            <>
              <h3 className="warn-h">Not exercised in the sandbox</h3>
              <ul>
                {review.untested.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </>
          )}
          {review.manual_followups?.length > 0 && (
            <>
              <h3>Still manual</h3>
              <ul>
                {review.manual_followups.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </section>
  )
}

function downloadScript(record, version) {
  const script = record.scripts.find((s) => s.version === version)
  const name = (record.parsed?.title ?? 'runbook').toLowerCase().replace(/[^a-z0-9]+/g, '-')
  const url = URL.createObjectURL(new Blob([script.script], { type: 'text/x-shellscript' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: `${name}-v${version}.sh` })
  a.click()
  URL.revokeObjectURL(url)
}

const DECISION_LABEL = { approved: 'approved', rejected: 'rejected', sent_back: 'asked for changes to' }

export function ApprovalPanel({ record, act }) {
  const { user, can } = useSession()
  const [comment, setComment] = useState('')
  const { pending, error, run } = useAction()

  const version = record.review.script_version
  const needed = record.parsed?.risk_tier === 'high' ? 2 : 1
  const decisions = (record.approvals ?? []).filter((a) => a.script_version === version)
  const approvedCount = decisions.filter((a) => a.decision === 'approved').length
  const ownRunbook = record.submitted_by === user.id
  const alreadyApproved = decisions.some((d) => d.decision === 'approved' && d.user_id === user.id)
  const blocked = !can('approver')
    ? 'You need the approver role to review scripts.'
    : ownRunbook
      ? 'You uploaded this runbook, so someone else has to review it.'
      : alreadyApproved
        ? 'You have approved this version; a second approver is needed.'
        : null

  const tone = { approved: 'panel-good', rejected: 'panel-bad' }[record.status] ?? ''
  const title = { approved: 'Approved: in the automation library', rejected: 'Rejected' }[record.status] ?? 'Engineer approval'

  const rejectFinal = () => {
    if (window.confirm(`Reject v${version} for good? Nothing will be rebuilt; the reason is kept in the audit log.`)) {
      run(async () => {
        await act(api.reject(record.id, comment))
        setComment('')
      })
    }
  }

  return (
    <section className={`panel ${tone}`}>
      <div className="panel-head">
        <h2>{title}</h2>
        <span className="muted">
          {approvedCount} of {needed} approval{needed === 1 ? '' : 's'} · {record.parsed?.risk_tier} risk
          {record.submitted_by_name && ` · uploaded by ${record.submitted_by_name}`}
        </span>
      </div>

      {decisions.length > 0 && (
        <ul className="decisions">
          {decisions.map((d, i) => (
            <li key={i} className={d.decision}>
              <strong>{d.reviewer}</strong> {DECISION_LABEL[d.decision] ?? d.decision} v{d.script_version} at {clockTime(d.at)}
              {d.comment && <span className="muted">: "{d.comment}"</span>}
            </li>
          ))}
        </ul>
      )}

      {record.status === 'awaiting_approval' &&
        (blocked ? (
          <p className="muted small">{blocked}</p>
        ) : (
          <>
            <input
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Comment: what to change, or why you reject it (required for both)"
            />
            <div className="actions">
              <span className="muted small">Reviewing as {user.display_name}</span>
              {error && <span className="error-text">{error}</span>}
              <button
                className="btn btn-danger"
                disabled={pending || !comment.trim()}
                title="Final: nothing is rebuilt"
                onClick={rejectFinal}
              >
                Reject
              </button>
              <button
                className="btn btn-ghost"
                disabled={pending || !comment.trim()}
                title="The Author rewrites the script from your comment; the new version is tested and reviewed again"
                onClick={() => run(() => act(api.requestChanges(record.id, comment)))}
              >
                Request changes
              </button>
              <button className="btn btn-primary" disabled={pending} onClick={() => run(() => act(api.approve(record.id, comment)))}>
                Approve v{version}
              </button>
            </div>
          </>
        ))}

      {record.status === 'rejected' && !can('submitter') && <p className="muted small">Nothing will run. A submitter can reopen it.</p>}
      {record.status === 'rejected' && can('submitter') && (
        <>
          <textarea
            rows={2}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Optional: guidance for the Author agent if you reopen it"
          />
          <div className="actions">
            <span className="muted small">Nothing will run. Reopening writes a new version that is tested and reviewed again.</span>
            {error && <span className="error-text">{error}</span>}
            <button className="btn btn-ghost" disabled={pending} onClick={() => run(() => act(api.build(record.id, comment)))}>
              Reopen: rewrite and retest
            </button>
          </div>
        </>
      )}

      {record.status === 'approved' && (
        <div className="actions">
          <span className="muted small">Run it on servers from the Run panel below. Every run is logged.</span>
          <button className="btn btn-ghost" onClick={() => downloadScript(record, record.approved_version)}>
            Download script v{record.approved_version}
          </button>
        </div>
      )}
    </section>
  )
}
