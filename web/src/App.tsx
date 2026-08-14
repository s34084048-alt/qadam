import { useEffect, useState } from 'react'
import { BrowserRouter, Navigate, NavLink, Route, Routes } from 'react-router-dom'
import { api, session } from './api'
import { OfflineBar } from './components/OfflineBar'
import { SafetyBanner } from './components/SafetyBanner'
import { useI18n } from './i18n'
import { CaseDetail } from './pages/CaseDetail'
import { Cases } from './pages/Cases'
import { Emergency } from './pages/Emergency'
import { Fairness } from './pages/Fairness'
import { Login } from './pages/Login'
import { NewCase } from './pages/NewCase'
import type { SafetyBlock } from './types'

function Shell({ onSignOut, safety }: { onSignOut: () => void; safety: SafetyBlock | null }) {
  const { t, toggle } = useI18n()
  return (
    <>
      <header className="topbar">
        <span className="brand">{t('app.name')}</span>
        <span className="tagline">{t('app.tagline')}</span>
        <nav>
          <NavLink to="/new" className={({ isActive }) => (isActive ? 'active' : '')}>
            {t('nav.new')}
          </NavLink>
          <NavLink to="/cases" className={({ isActive }) => (isActive ? 'active' : '')}>
            {t('nav.cases')}
          </NavLink>
          <NavLink to="/emergency" className={({ isActive }) => (isActive ? 'active' : '')}>
            {t('nav.emergency')}
          </NavLink>
          {session.role === 'admin' && (
            <NavLink to="/fairness" className={({ isActive }) => (isActive ? 'active' : '')}>
              {t('nav.fairness')}
            </NavLink>
          )}
          <button className="link" type="button" onClick={toggle}>
            {t('nav.language')}
          </button>
          <span className="who">{session.email}</span>
          <button className="link" type="button" onClick={onSignOut}>
            {t('nav.signout')}
          </button>
        </nav>
      </header>

      <main>
        <Routes>
          <Route path="/new" element={<NewCase />} />
          <Route path="/cases" element={<Cases />} />
          <Route path="/cases/:caseId" element={<CaseDetail />} />
          <Route path="/emergency" element={<Emergency />} />
          <Route path="/fairness" element={<Fairness />} />
          <Route path="*" element={<Navigate to="/new" replace />} />
        </Routes>

        {safety && (
          <footer className="footer-note">
            <p><strong>{t('common.intendedUse')}:</strong> {safety.intended_use}</p>
            <p>
              {safety.scope} {safety.no_treatment}
              {safety.data_residency
                ? ` Data residency: ${safety.data_residency}.` : ''}
            </p>
          </footer>
        )}
      </main>
    </>
  )
}

export default function App() {
  const [signedIn, setSignedIn] = useState(Boolean(session.token))
  const [safety, setSafety] = useState<SafetyBlock | null>(null)
  const [entering, setEntering] = useState(false)

  useEffect(() => {
    api.safety().then(setSafety).catch(() => setSafety(null))
  }, [])

  // Open access with no sign-in screen at all: when the server reports demo
  // mode and there is no session yet, start one and go straight in.
  //
  // This removes a form, not a boundary. Each visitor still gets their OWN
  // organisation, so nobody sees anybody else's patients, cases or images —
  // that isolation is what makes open access defensible, and it is unchanged.
  // If it fails for any reason the sign-in form is still there underneath.
  useEffect(() => {
    if (signedIn) return
    let cancelled = false
    setEntering(true)
    api.health()
      .then(async (h) => {
        if (cancelled || !h.demo_mode) return
        await api.startDemo()
        if (!cancelled) setSignedIn(true)
      })
      .catch(() => { /* fall through to the sign-in form */ })
      .finally(() => { if (!cancelled) setEntering(false) })
    return () => { cancelled = true }
  }, [signedIn])

  function signOut() {
    session.clear()
    setSignedIn(false)
  }

  return (
    <BrowserRouter>
      <SafetyBanner />
      <OfflineBar />
      {signedIn
        ? <Shell onSignOut={signOut} safety={safety} />
        : entering
          ? <main><p className="hint">Starting…</p></main>
          : <Login onDone={() => setSignedIn(true)} />}
    </BrowserRouter>
  )
}
