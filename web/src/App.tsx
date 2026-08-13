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

  useEffect(() => {
    api.safety().then(setSafety).catch(() => setSafety(null))
  }, [])

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
        : <Login onDone={() => setSignedIn(true)} />}
    </BrowserRouter>
  )
}
