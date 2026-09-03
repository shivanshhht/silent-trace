import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function App() {
  const [health, setHealth] = useState({ state: 'checking', message: 'Checking backend connection…' })

  useEffect(() => {
    fetch(`${API_URL}/api/health`)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json()
      })
      .then((data) => {
        setHealth({ state: 'connected', message: data.service || 'Backend connected' })
      })
      .catch(() => {
        setHealth({ state: 'unavailable', message: 'Start the FastAPI server on port 8000' })
      })
  }, [])

  return (
    <main className="shell">
      <section className="hero" aria-labelledby="page-title">
        <div className="eyebrow">INVESTIGATION INTELLIGENCE PLATFORM</div>
        <h1 id="page-title">Silent <span>Trace</span></h1>
        <p className="intro">A focused foundation for explainable, time-aware analysis of synthetic investigative data.</p>
        <div className={`status-card ${health.state}`} role="status">
          <span className="status-dot" aria-hidden="true" />
          <div>
            <strong>{health.state === 'connected' ? 'Backend connected' : health.state === 'unavailable' ? 'Backend unavailable' : 'Connecting to backend'}</strong>
            <small>{health.message}</small>
          </div>
        </div>
      </section>
      <footer>Phase 1 foundation · Synthetic data only</footer>
    </main>
  )
}

createRoot(document.getElementById('root')).render(
  <StrictMode><App /></StrictMode>,
)
