import { useMemo } from 'react'
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import { STATUS_LABELS, statusTone } from '../api.js'

hljs.registerLanguage('bash', bash)

export function StatusChip({ status }) {
  const tone = statusTone(status)
  return (
    <span className={`chip chip-${tone}`}>
      {tone === 'busy' && <span className="spinner" />}
      {STATUS_LABELS[status] ?? status}
    </span>
  )
}

export function RiskBadge({ tier }) {
  if (!tier) return null
  return <span className={`risk risk-${tier}`}>{tier[0].toUpperCase() + tier.slice(1)} risk</span>
}

const STEP_LABELS = { OK: 'Pass', SKIP: 'Skipped', FAIL: 'Fail' }

export function StepBadge({ label, status }) {
  const tone = { OK: 'good', SKIP: 'neutral', FAIL: 'bad' }[status] ?? 'none'
  return (
    <span className={`step-badge sb-${tone}`} title={label}>
      <span className="sb-label">{label}</span>
      <span className="sb-value">{STEP_LABELS[status] ?? 'Not run'}</span>
    </span>
  )
}

export function Code({ code, className = '' }) {
  const html = useMemo(() => hljs.highlight(code ?? '', { language: 'bash' }).value, [code])
  return (
    <pre className={`code ${className}`}>
      <code className="hljs" dangerouslySetInnerHTML={{ __html: html }} />
    </pre>
  )
}

export function timeAgo(iso) {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`
  return new Date(iso).toLocaleDateString()
}

export function clockTime(iso) {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}
