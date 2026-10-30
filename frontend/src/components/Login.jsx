import { useEffect, useState } from 'react'
import { api } from '../api.js'

async function signInWithMicrosoft(config) {
  // Loaded only when used, so the Microsoft library isn't downloaded unless Entra is configured.
  const { PublicClientApplication } = await import('@azure/msal-browser')
  const msal = new PublicClientApplication({
    auth: {
      clientId: config.entra_client_id,
      authority: `https://login.microsoftonline.com/${config.entra_tenant_id}`,
      redirectUri: window.location.origin,
    },
  })
  await msal.initialize()
  const result = await msal.loginPopup({ scopes: ['openid', 'profile', 'email'] })
  return api.loginEntra(result.idToken)
}

export default function Login({ onSignedIn }) {
  const [config, setConfig] = useState(null)
  const [form, setForm] = useState({ username: '', password: '', displayName: '' })
  const [error, setError] = useState(null)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    api.authConfig().then(setConfig).catch((e) => setError(e.message))
  }, [])

  const setup = config?.needs_setup

  async function submit(e) {
    e.preventDefault()
    setPending(true)
    setError(null)
    try {
      const result = setup
        ? await api.setup(form.username, form.password, form.displayName)
        : await api.login(form.username, form.password)
      onSignedIn(result.user)
    } catch (err) {
      setError(err.message)
      setPending(false)
    }
  }

  async function microsoft() {
    setPending(true)
    setError(null)
    try {
      onSignedIn((await signInWithMicrosoft(config)).user)
    } catch (err) {
      setError(err.message)
      setPending(false)
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit}>
        <div className="login-brand">
          <span className="brand-mark" aria-hidden="true" />
          <span className="strong">RunbookPilot</span>
        </div>
        <p className="muted small login-tagline">Runbooks in, tested automation out.</p>

        <h1>{setup ? 'Create the first admin' : 'Sign in'}</h1>
        {setup && (
          <p className="muted small">
            No accounts exist yet. This account becomes the administrator; it can then add everyone else.
          </p>
        )}

        {config?.entra && !setup && (
          <>
            <button type="button" className="btn btn-ms" onClick={microsoft} disabled={pending}>
              <span className="ms-logo" aria-hidden="true">
                <i />
                <i />
                <i />
                <i />
              </span>
              Sign in with Microsoft
            </button>
            <div className="divider">
              <span>or with a local account</span>
            </div>
          </>
        )}

        <label>
          Username
          <input
            autoFocus
            autoComplete="username"
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
          />
        </label>
        {setup && (
          <label>
            Display name
            <input value={form.displayName} onChange={(e) => setForm({ ...form, displayName: e.target.value })} />
          </label>
        )}
        <label>
          Password
          <input
            type="password"
            autoComplete={setup ? 'new-password' : 'current-password'}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </label>
        {setup && <span className="muted small">At least 8 characters.</span>}

        {error && <div className="error-text">{error}</div>}
        <button className="btn btn-primary" disabled={pending || !form.username || !form.password}>
          {pending ? 'Please wait…' : setup ? 'Create admin and sign in' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
