import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { RiskBadge, StatusChip } from './common.jsx'

const fmt = (n, digits = 0) =>
  n == null ? '–' : Number(n).toLocaleString(undefined, { maximumFractionDigits: digits })

function Tile({ value, label, sub }) {
  return (
    <div className="tile">
      <div className="tile-value">{value}</div>
      <div className="tile-label">{label}</div>
      {sub && <div className="tile-sub">{sub}</div>}
    </div>
  )
}

// Single-series horizontal bars: hours saved per year, sorted, with a hover tooltip per bar.
function HoursChart({ rows }) {
  const [hover, setHover] = useState(null)
  const data = rows.filter((r) => r.hours_saved_per_year != null).sort((a, b) => b.hours_saved_per_year - a.hours_saved_per_year)
  if (!data.length) return <div className="empty">No converted runbooks with manual-time data yet.</div>
  const max = Math.max(...data.map((r) => r.hours_saved_per_year))

  return (
    <div className="hbar-chart" role="img" aria-label="Engineer hours saved per year by runbook">
      {data.map((r) => (
        <div
          key={r.id}
          className={`hbar-row ${hover?.id === r.id ? 'hover' : ''}`}
          onMouseEnter={() => setHover(r)}
          onMouseLeave={() => setHover(null)}
          onClick={() => (window.location.hash = `#/runbooks/${r.id}`)}
        >
          <span className="hbar-label" title={r.title}>
            {r.title}
          </span>
          <span className="hbar-track">
            <span className="hbar-fill" style={{ width: `${(r.hours_saved_per_year / max) * 100}%` }} />
            <span className="hbar-value">{fmt(r.hours_saved_per_year)} h</span>
          </span>
          {hover?.id === r.id && (
            <span className="tooltip">
              <strong>{r.title}</strong>
              <span>
                {fmt(r.manual_minutes)} min by hand → ~2 min automated
              </span>
              <span>
                {fmt(r.runs_per_month)} runs a month · {fmt(r.speedup, 1)}× faster
              </span>
              <span>
                <strong>{fmt(r.hours_saved_per_year, 1)} hours saved a year</strong>
              </span>
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.metrics().then(setData).catch((e) => setError(e.message))
  }, [])

  if (error) return <div className="panel error-text">{error}</div>
  if (!data) return <div className="panel muted">Loading…</div>

  const t = data.totals
  const rate = t.processed ? Math.round((t.converted / t.processed) * 100) : 0

  return (
    <div className="stack">
      <div>
        <h1>Impact</h1>
        <p className="muted">What RunbookPilot has converted so far, and what it would save if those scripts replaced manual runs.</p>
      </div>

      <div className="tiles">
        <Tile value={`${t.converted} / ${t.processed}`} label="runbooks converted" sub={`${rate}% passed sandbox tests`} />
        <Tile value={`${t.first_attempt} / ${t.converted}`} label="passed on the first try" sub="the rest were fixed by the Tester loop" />
        <Tile value={t.avg_minutes_to_automate != null ? `${fmt(t.avg_minutes_to_automate, 1)} min` : '–'} label="avg time to automate" sub="upload to approval-ready, vs days by hand" />
        <Tile value={fmt(t.hours_saved_per_year)} label="engineer hours saved / year" sub={`across ${fmt(t.manual_runs_per_year)} manual runs a year`} />
      </div>

      <section className="panel">
        <div className="panel-head">
          <h2>Measured from real runs</h2>
          <span className="muted small">approved scripts executed on servers</span>
        </div>
        {data.measured?.execute_runs ? (
          <div className="tiles tiles-flat">
            <Tile value={fmt(data.measured.execute_runs)} label="execute runs" sub={`${fmt(data.measured.hands_off_runs)} started by schedules or alerts`} />
            <Tile value={`${fmt(data.measured.success_rate)}%`} label="succeeded" sub={`${fmt(data.measured.succeeded)} runs`} />
            <Tile value={`${fmt(data.measured.avg_run_seconds, 1)} s`} label="average run time" sub="dry run + execute, end to end" />
            <Tile value={fmt(data.measured.hours_saved, 1)} label="engineer hours saved so far" sub="manual time minus actual run time" />
          </div>
        ) : (
          <div className="empty">No scripts have run on servers yet. Approve a runbook, then run it from its page.</div>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Hours saved per year, by runbook (projected)</h2>
          <span className="muted small">(manual min − 2 min) × runs per year ÷ 60</span>
        </div>
        <HoursChart rows={data.runbooks} />
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>All runbooks</h2>
          <span className="muted small">{t.questions_asked} questions asked instead of guessing</span>
        </div>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Runbook</th>
                <th>Risk</th>
                <th>Status</th>
                <th className="num">Tries</th>
                <th className="num">To automate</th>
                <th className="num">Manual</th>
                <th className="num">Script run</th>
                <th className="num">Runs/mo</th>
                <th className="num">Hours/yr saved</th>
              </tr>
            </thead>
            <tbody>
              {data.runbooks.map((r) => (
                <tr key={r.id} onClick={() => (window.location.hash = `#/runbooks/${r.id}`)}>
                  <td className="strong">{r.title}</td>
                  <td><RiskBadge tier={r.risk_tier} /></td>
                  <td><StatusChip status={r.status} /></td>
                  <td className="num">{fmt(r.attempts)}</td>
                  <td className="num">{r.minutes_to_automate != null ? `${fmt(r.minutes_to_automate, 1)} min` : '–'}</td>
                  <td className="num">{r.manual_minutes != null ? `${fmt(r.manual_minutes)} min` : '–'}</td>
                  <td className="num">{r.script_seconds != null ? `${fmt(r.script_seconds, 1)} s` : '–'}</td>
                  <td className="num">{fmt(r.runs_per_month)}</td>
                  <td className="num strong">{fmt(r.hours_saved_per_year)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small assumption">{data.assumptions.note} Replace the runbooks' manual times and frequencies with your team's real numbers before quoting them.</p>
      </section>
    </div>
  )
}
