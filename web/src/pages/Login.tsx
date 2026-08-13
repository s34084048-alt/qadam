import { useEffect, useState } from 'react'
import { api } from '../api'
import { ErrorPanel } from '../components/ErrorPanel'
import { useI18n } from '../i18n'

/** Accounts created by `python -m app.seed`. Offered only when the API reports
 *  environment=local, so they can never appear in a deployed instance. */
const SEEDED = [
  { email: 'clinician@qadam.local', password: 'qadam-clinician', role: 'clinician' },
  { email: 'admin@qadam.local', password: 'qadam-admin', role: 'admin' },
]

export function Login({ onDone }: { onDone: () => void }) {
  const { t } = useI18n()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [isLocal, setIsLocal] = useState(false)

  useEffect(() => {
    api.health()
      .then((h) => setIsLocal(h.environment === 'local'))
      .catch(() => setIsLocal(false))
  }, [])

  async function signIn(withEmail: string, withPassword: string) {
    setBusy(true)
    setError(null)
    try {
      await api.login(withEmail.trim(), withPassword)
      onDone()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main style={{ maxWidth: 420 }}>
      <form
        className="card"
        onSubmit={(event) => { event.preventDefault(); void signIn(email, password) }}
      >
        <h1>{t('login.title')}</h1>
        <p className="hint">{t('login.role')}</p>
        <ErrorPanel error={error} />
        <div className="field">
          <label htmlFor="email">{t('login.email')}</label>
          <input
            id="email" type="email" value={email} autoComplete="username"
            autoCapitalize="none" autoCorrect="off" spellCheck={false}
            onChange={(e) => setEmail(e.target.value)} required
          />
        </div>
        <div className="field">
          <label htmlFor="password">{t('login.password')}</label>
          <input
            id="password" type="password" value={password} autoComplete="current-password"
            autoCapitalize="none" autoCorrect="off" spellCheck={false}
            onChange={(e) => setPassword(e.target.value)} required
          />
        </div>
        <button type="submit" disabled={busy}>
          {busy ? t('login.working') : t('login.submit')}
        </button>

        {isLocal && (
          <div className="demo-accounts">
            <p>{t('login.demoAccounts')}</p>
            {SEEDED.map((account) => (
              <button
                key={account.email}
                type="button"
                className="ghost"
                disabled={busy}
                onClick={() => {
                  setEmail(account.email)
                  setPassword(account.password)
                  void signIn(account.email, account.password)
                }}
              >
                {account.role} — {account.email}
              </button>
            ))}
          </div>
        )}
      </form>
    </main>
  )
}
