import { useEffect, useState } from 'react'
import { Code, StepBadge } from './common.jsx'

// Pull one step's function (plus the comment right above it) out of the full script.
function extractFunction(script, order, name) {
  const lines = script.split('\n')
  const pattern = name
    ? new RegExp(`^\\s*(function\\s+)?${name}\\s*\\(\\)`)
    : new RegExp(`^\\s*(function\\s+)?step_${order}_\\w*\\s*\\(\\)`)
  const start = lines.findIndex((l) => pattern.test(l))
  if (start < 0) return null
  let end = lines.length - 1
  for (let i = start + 1; i < lines.length; i++) {
    if (/^\}\s*$/.test(lines[i])) {
      end = i
      break
    }
  }
  let from = start
  while (from > 0 && /^\s*#(?!!)/.test(lines[from - 1])) from--
  return lines.slice(from, end + 1).join('\n')
}

function stepStatus(run, stage, order) {
  return run?.[stage]?.steps?.find((s) => s.order === order)
}

function SideBySide({ record, script, run }) {
  const steps = record.parsed.steps
  return (
    <div className="sbs">
      <div className="sbs-head">
        <span>Runbook step</span>
        <span>Generated code {script ? `(v${script.version})` : ''}</span>
      </div>
      {steps.map((step) => {
        const fn = script?.steps?.find((s) => s.order === step.order)
        const code = script ? extractFunction(script.script, step.order, fn?.function) : null
        const dry = stepStatus(run, 'dry_run', step.order)
        const exec = stepStatus(run, 'execute', step.order)
        const message = (exec ?? dry)?.messages?.at(-1)
        return (
          <div key={step.order} className={`sbs-row ${exec?.status === 'FAIL' || dry?.status === 'FAIL' ? 'row-fail' : ''}`}>
            <div className="sbs-step">
              <div className="step-num">{step.order}</div>
              <div className="step-body">
                <div className="step-action">{step.action}</div>
                {step.target && <div className="muted small">on {step.target}</div>}
                {step.command && <code className="inline-cmd">{step.command}</code>}
                {step.expected_result && (
                  <div className="small">
                    <span className="muted">Expect: </span>
                    {step.expected_result}
                  </div>
                )}
                {step.question && (
                  <div className="qa small">
                    <div>
                      <span className="q-mark">?</span> {step.question}
                    </div>
                    {step.answer ? (
                      <div className="answer">↳ {step.answer}</div>
                    ) : (
                      <div className="muted">Waiting for an answer</div>
                    )}
                  </div>
                )}
                {step.changes_system && <span className="tag tag-warn">changes system</span>}
              </div>
            </div>
            <div className="sbs-code">
              {code ? (
                <Code code={code} />
              ) : (
                <div className="code-placeholder">
                  {record.status === 'writing_script' ? 'The Author agent is writing this step…' : script ? 'No matching function' : 'No script yet'}
                </div>
              )}
              {run && (
                <div className="badges">
                  <StepBadge label="Dry run" status={dry?.status} />
                  <StepBadge label="Execute" status={exec?.status} />
                  {message && <span className="badge-msg muted small">{message}</span>}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function FullScript({ script }) {
  const lint = script.lint
  return (
    <div className="stack-sm">
      <div className="lint-row">
        <span className={`chip chip-${lint.passed ? 'good' : 'bad'}`}>Lint {lint.passed ? 'passed' : 'blocked'}</span>
        <span className="muted small">
          {lint.blocked.length} blocked command(s) · {lint.issues.length} ShellCheck warning(s)
        </span>
      </div>
      {[...lint.blocked, ...lint.issues].length > 0 && (
        <ul className="lint-issues">
          {[...lint.blocked, ...lint.issues].map((i, k) => (
            <li key={k} className={`sev-${i.severity}`}>
              line {i.line}: {i.message}
            </li>
          ))}
        </ul>
      )}
      {script.notes?.length > 0 && (
        <div className="notes">
          <h3>Author notes</h3>
          <ul>
            {script.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </div>
      )}
      {script.feedback && (
        <div className="notes">
          <h3>Written in response to</h3>
          <p className="small pre">{script.feedback}</p>
        </div>
      )}
      <Code code={script.script} className="code-full" />
    </div>
  )
}

function TestRuns({ runs }) {
  if (!runs?.length) return <div className="empty">No sandbox runs yet.</div>
  return (
    <div className="stack-sm">
      {runs.map((run, i) => (
        <details key={i} className={`run ${run.passed ? 'run-pass' : 'run-fail'}`} open={i === runs.length - 1}>
          <summary>
            <span className={`chip chip-${run.passed ? 'good' : 'bad'}`}>{run.passed ? 'Passed' : `Failed: ${run.failed_stage}`}</span>
            <span>
              Attempt {run.attempt} · script v{run.script_version}
            </span>
            {['dry_run', 'execute'].map(
              (stage) =>
                run[stage] && (
                  <span key={stage} className="muted small">
                    {stage === 'dry_run' ? 'dry run' : 'execute'}: exit {run[stage].exit_code}, {run[stage].duration_s}s
                  </span>
                ),
            )}
          </summary>
          {run.diagnosis && (
            <div className="diagnosis">
              <span className="tag">Tester: {run.diagnosis.category?.replace('_', ' ')}</span>
              <p>{run.diagnosis.diagnosis}</p>
              {run.diagnosis.fix && <p className="muted small">Fix requested: {run.diagnosis.fix}</p>}
            </div>
          )}
          {['dry_run', 'execute'].map(
            (stage) =>
              run[stage] && (
                <div key={stage}>
                  <h3>{stage === 'dry_run' ? 'Dry run output' : 'Execute output'}</h3>
                  <pre className="console">{run[stage].stdout || '(no output)'}{run[stage].stderr ? `\n--- stderr ---\n${run[stage].stderr}` : ''}</pre>
                </div>
              ),
          )}
        </details>
      ))}
    </div>
  )
}

export default function StepReview({ record }) {
  const scripts = record.scripts ?? []
  const [tab, setTab] = useState('sbs')
  const [version, setVersion] = useState(null)
  const latest = scripts.at(-1)?.version

  // Follow the newest version as the agents produce it, unless the user picked one.
  useEffect(() => setVersion(null), [latest])

  const script = scripts.find((s) => s.version === (version ?? latest))
  const run = [...(record.test_runs ?? [])].reverse().find((r) => r.script_version === script?.version)

  return (
    <section className="panel">
      <div className="panel-head tabs-head">
        <div className="tabs">
          <button className={tab === 'sbs' ? 'active' : ''} onClick={() => setTab('sbs')}>
            Side by side
          </button>
          <button className={tab === 'script' ? 'active' : ''} onClick={() => setTab('script')} disabled={!script}>
            Full script
          </button>
          <button className={tab === 'runs' ? 'active' : ''} onClick={() => setTab('runs')}>
            Sandbox runs {record.test_runs?.length ? `(${record.test_runs.length})` : ''}
          </button>
        </div>
        {scripts.length > 1 && tab !== 'runs' && (
          <select value={script?.version} onChange={(e) => setVersion(Number(e.target.value))}>
            {scripts.map((s) => (
              <option key={s.version} value={s.version}>
                Script v{s.version}
                {s.version === latest ? ' (latest)' : ''}
              </option>
            ))}
          </select>
        )}
      </div>
      {tab === 'sbs' && <SideBySide record={record} script={script} run={run} />}
      {tab === 'script' && script && <FullScript script={script} />}
      {tab === 'runs' && <TestRuns runs={record.test_runs} />}
    </section>
  )
}
