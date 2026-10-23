import { useState } from 'react'
import { api } from '../api.js'
import { clockTime } from './common.jsx'

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
      {kind === 'error' && <p className="mono small">{record.error}</p>}
      {diagnosis && (
        <div className="diagnosis">
          <span className="tag">{diagnosis.category?.replace('_', ' ')}</span>
          {diagnosis.failed_step && <span className="tag">step {diagnosis.failed_step}</span>}
          <p>{diagnosis.diagnosis}</p>
        </div>
      )}
      {canRebuild && (
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

export function ApprovalPanel({ record, act }) {
  const [reviewer, setReviewer] = useState(() => {
    try {
      return localStorage.getItem('rbp-reviewer') ?? ''
    } catch {
      return ''
    }
  })
  const [comment, setComment] = useState('')
  const { pending, error, run } = useAction()

  const version = record.review.script_version
  const needed = record.parsed?.risk_tier === 'high' ? 2 : 1
  const decisions = (record.approvals ?? []).filter((a) => a.script_version === version)
  const approvedCount = decisions.filter((a) => a.decision === 'approved').length

  function remember() {
    try {
      localStorage.setItem('rbp-reviewer', reviewer)
    } catch {
      /* storage unavailable: name just isn't remembered */
    }
  }

  return (
    <section className={`panel ${record.status === 'approved' ? 'panel-good' : ''}`}>
      <div className="panel-head">
        <h2>{record.status === 'approved' ? 'Approved: in the automation library' : 'Engineer approval'}</h2>
        <span className="muted">
          {approvedCount} of {needed} approval{needed === 1 ? '' : 's'} · {record.parsed?.risk_tier} risk
        </span>
      </div>

      {decisions.length > 0 && (
        <ul className="decisions">
          {decisions.map((d, i) => (
            <li key={i} className={d.decision}>
              <strong>{d.reviewer}</strong> {d.decision} v{d.script_version} at {clockTime(d.at)}
              {d.comment && <span className="muted">: "{d.comment}"</span>}
            </li>
          ))}
        </ul>
      )}

      {record.status === 'awaiting_approval' && (
        <>
          <div className="approve-form">
            <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="Your name" />
            <input
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Comment (required to reject; goes back to the Author agent)"
            />
          </div>
          <div className="actions">
            {error && <span className="error-text">{error}</span>}
            <button
              className="btn btn-danger"
              disabled={pending || !reviewer.trim() || !comment.trim()}
              onClick={() => run(async () => { remember(); await act(api.reject(record.id, reviewer, comment)) })}
            >
              Reject and send back
            </button>
            <button
              className="btn btn-primary"
              disabled={pending || !reviewer.trim()}
              onClick={() => run(async () => { remember(); await act(api.approve(record.id, reviewer, comment)) })}
            >
              Approve v{version}
            </button>
          </div>
        </>
      )}

      {record.status === 'approved' && (
        <div className="actions">
          <span className="muted small">Every run of this script is logged. Production runs go through Azure Automation / Ansible (next phase).</span>
          <button className="btn btn-primary" onClick={() => downloadScript(record, record.approved_version)}>
            Download script v{record.approved_version}
          </button>
        </div>
      )}
    </section>
  )
}
