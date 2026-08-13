import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { I18nProvider } from './i18n'
import { OfflineProvider } from './offline/OfflineContext'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <I18nProvider>
      <OfflineProvider>
        <App />
      </OfflineProvider>
    </I18nProvider>
  </StrictMode>,
)

// After one successful online visit the interface opens with no connection.
// Registration failures are non-fatal: the app simply stays online-only.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    void navigator.serviceWorker.register('/sw.js').catch(() => undefined)
  })
}
