const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(BASE + path, options)
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(body.detail || `${res.status} ${res.statusText}`)
  return body
}

const post = (path, data) =>
  request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data ?? {}),
  })

export const api = {
  health: () => request('/health'),
  sandbox: () => request('/sandbox'),
  list: () => request('/runbooks'),
  get: (id) => request(`/runbooks/${id}`),
  remove: (id) => request(`/runbooks/${id}`, { method: 'DELETE' }),
  upload: (file) => {
    const form = new FormData()
    form.append('file', file)
    return request('/runbooks', { method: 'POST', body: form })
  },
  answer: (id, answers) => post(`/runbooks/${id}/answers`, { answers }),
  build: (id, feedback) => post(`/runbooks/${id}/build`, { feedback: feedback || null }),
  approve: (id, reviewer, comment) => post(`/runbooks/${id}/approve`, { reviewer, comment }),
  reject: (id, reviewer, comment) => post(`/runbooks/${id}/reject`, { reviewer, comment }),
}

export const BUSY = new Set(['uploaded', 'parsing', 'writing_script', 'testing', 'reviewing'])

export const STATUS_LABELS = {
  uploaded: 'Uploaded',
  parsing: 'Parsing',
  needs_answers: 'Needs answers',
  parsed: 'Parsed',
  writing_script: 'Writing script',
  testing: 'Testing in sandbox',
  tests_failed: 'Tests failed',
  reviewing: 'Writing review',
  awaiting_approval: 'Awaiting approval',
  approved: 'Approved',
  rejected: 'Rejected',
  error: 'Error',
}

export function statusTone(status) {
  if (BUSY.has(status)) return 'busy'
  if (status === 'approved') return 'good'
  if (['needs_answers', 'awaiting_approval'].includes(status)) return 'attention'
  if (['tests_failed', 'rejected', 'error'].includes(status)) return 'bad'
  return 'neutral'
}
