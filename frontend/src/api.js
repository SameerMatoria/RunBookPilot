const BASE = '/api'

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function request(path, options = {}) {
  const res = await fetch(BASE + path, { credentials: 'same-origin', ...options })
  const body = await res.json().catch(() => ({}))
  if (res.status === 401 && !path.startsWith('/auth/')) {
    // Session expired or signed out elsewhere: tell the app to show the sign-in page.
    window.dispatchEvent(new Event('rbp:unauthorized'))
  }
  if (!res.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join('; ') : body.detail
    throw new ApiError(detail || `${res.status} ${res.statusText}`, res.status)
  }
  return body
}

const send = (method) => (path, data) =>
  request(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data ?? {}),
  })
const post = send('POST')
const patch = send('PATCH')
const del = (path) => request(path, { method: 'DELETE' })
const query = (params) => {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== ''))
  return q.toString() ? `?${q}` : ''
}

export const api = {
  // auth
  authConfig: () => request('/auth/config'),
  me: () => request('/auth/me'),
  login: (username, password) => post('/auth/login', { username, password }),
  loginEntra: (idToken) => post('/auth/entra', { id_token: idToken }),
  setup: (username, password, displayName) => post('/auth/setup', { username, password, display_name: displayName }),
  logout: () => post('/auth/logout'),

  // system
  health: () => request('/health'),
  sandbox: () => request('/sandbox'),
  metrics: () => request('/metrics'),

  // runbooks
  list: () => request('/runbooks'),
  get: (id) => request(`/runbooks/${id}`),
  remove: (id) => del(`/runbooks/${id}`),
  upload: (file) => {
    const form = new FormData()
    form.append('file', file)
    return request('/runbooks', { method: 'POST', body: form })
  },
  answer: (id, answers) => post(`/runbooks/${id}/answers`, { answers }),
  build: (id, feedback) => post(`/runbooks/${id}/build`, { feedback: feedback || null }),
  retry: (id) => post(`/runbooks/${id}/retry`),
  approve: (id, comment) => post(`/runbooks/${id}/approve`, { comment: comment || null }),
  reject: (id, comment) => post(`/runbooks/${id}/reject`, { comment }),

  // users and audit (admin)
  users: () => request('/users'),
  directory: () => request('/users/directory'),
  createUser: (data) => post('/users', data),
  updateUser: (id, data) => patch(`/users/${id}`, data),
  audit: (params = {}) => request(`/audit${query(params)}`),

  // servers and credentials
  servers: () => request('/servers'),
  createServer: (data) => post('/servers', data),
  updateServer: (id, data) => patch(`/servers/${id}`, data),
  deleteServer: (id) => del(`/servers/${id}`),
  testServer: (id) => post(`/servers/${id}/test`),
  credentials: () => request('/credentials'),
  createCredential: (data) => post('/credentials', data),
  deleteCredential: (id) => del(`/credentials/${id}`),

  // runs on real servers
  startRun: (runbookId, data) => post(`/runbooks/${runbookId}/runs`, data),
  runs: (params = {}) => request(`/runs${query(params)}`),
  run: (id) => request(`/runs/${id}`),
  cancelRun: (id) => post(`/runs/${id}/cancel`),

  // schedules and alert triggers
  schedules: (runbookId) => request(`/runbooks/${runbookId}/schedules`),
  createSchedule: (runbookId, data) => post(`/runbooks/${runbookId}/schedules`, data),
  updateSchedule: (id, data) => patch(`/schedules/${id}`, data),
  deleteSchedule: (id) => del(`/schedules/${id}`),
  triggers: (runbookId) => request(`/runbooks/${runbookId}/triggers`),
  createTrigger: (runbookId, data) => post(`/runbooks/${runbookId}/triggers`, data),
  deleteTrigger: (id) => del(`/triggers/${id}`),
}

export const BUSY = new Set(['queued', 'uploaded', 'parsing', 'writing_script', 'testing', 'reviewing'])

export const STATUS_LABELS = {
  queued: 'Queued',
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

export const ROLES = ['submitter', 'approver', 'operator', 'admin']

export const hasRole = (user, role) => !!user && (user.roles.includes('admin') || user.roles.includes(role))
