import { useEffect, useState } from 'react'
import Chat from './components/Chat'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export default function App() {
  const [goldenQuestions, setGoldenQuestions] = useState([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(() => {
    if (typeof window !== 'undefined' && window.location.hash === '#chat') return 'chat'
    return 'landing'
  })

  useEffect(() => {
    ;(async () => {
      try {
        const goldenRes = await fetch(`${API_BASE}/api/golden`)
        if (goldenRes.ok) {
          const goldenJson = await goldenRes.json()
          setGoldenQuestions(goldenJson.questions || [])
        }
      } catch {
        setGoldenQuestions([])
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const openChat = () => {
    setPage('chat')
    if (typeof window !== 'undefined') window.location.hash = 'chat'
  }

  const openLanding = () => {
    setPage('landing')
    if (typeof window !== 'undefined') window.location.hash = ''
  }

  return (
    <div className="app">
      <div className="app-container">
        <header className="app-header">
          <div className="app-header-content">
            <div>
              <h1 className="app-title">Cast AI<span className="brand-dot">.</span></h1>
            </div>
            <div className="app-header-actions">
              {page === 'chat' ? (
                <button className="app-link-btn" onClick={openLanding}>Home</button>
              ) : (
                <button className="app-link-btn" onClick={openChat}>Chat</button>
              )}
            </div>
          </div>
        </header>

        <main className="app-main">
          {page === 'landing' ? (
            <Landing onChatNow={openChat} loading={loading} />
          ) : loading ? (
            <div className="app-loading">
              <span className="spinner spinner--lg" />
              <p>Connecting…</p>
            </div>
          ) : (
            <Chat goldenQuestions={goldenQuestions} />
          )}
        </main>
      </div>
    </div>
  )
}

function Landing({ onChatNow, loading }) {
  const sampleAnswer = [
    '• Provide targeted support [Paper 3]',
    '• Collect better empirical evacuation data [Paper 3]',
    '• Treat evacuation as a sequence of decisions [Paper 3]',
  ].join('\n')
  const [typedAnswer, setTypedAnswer] = useState('')

  useEffect(() => {
    if (loading) {
      setTypedAnswer('')
      return
    }

    let timeoutId = null
    let running = true

    const typeNext = (idx) => {
      if (!running) return
      setTypedAnswer(sampleAnswer.slice(0, idx))
      if (idx < sampleAnswer.length) {
        timeoutId = setTimeout(() => typeNext(idx + 1), 16)
      }
    }

    timeoutId = setTimeout(() => typeNext(1), 500)

    return () => {
      running = false
      if (timeoutId) clearTimeout(timeoutId)
    }
  }, [loading])

  const renderTypedMockText = (text) => {
    const parts = text.split(/(\[[^\]]+\])/g)
    return parts.map((part, idx) => {
      if (/^\[[^\]]+\]$/.test(part)) {
        return (
          <span key={`cite-${idx}`} className="mock-chat__cite-inline">
            {part}
          </span>
        )
      }
      return <span key={`txt-${idx}`}>{part}</span>
    })
  }

  return (
    <section className="landing">
      <div className="landing__copy">
        <p className="landing__label">Evidence-grounded Research Assistant</p>
        <h2 className="landing__title">Get better answers to disaster questions</h2>
        <p className="landing__text">
          Cast AI helps you explore wildfire research with concise, cited answers from indexed papers.
        </p>
        <button className="landing__cta" onClick={onChatNow} disabled={loading}>
          {loading ? 'Preparing Chat...' : 'Chat now'}
        </button>
      </div>

      <div className="landing__mockup" aria-hidden="true">
        <div className="mock-chat">
          <div className="mock-chat__bar">Cast AI Chat Preview</div>
          <div className="mock-chat__body">
            <div className="mock-chat__user">What should emergency managers do to improve wildfire evacuation planning?</div>
            <div className="mock-chat__bot">
              <p>
                <span className={`mock-chat__typing ${typedAnswer.length < sampleAnswer.length ? 'is-typing' : ''}`}>
                  {renderTypedMockText(typedAnswer)}
                </span>
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
