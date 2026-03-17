import { useState, useRef, useEffect, useCallback } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

// ---------------------------------------------------------------------------
// Bullet parser – turns "- Text [Paper N]" lines into structured data
// ---------------------------------------------------------------------------
function parseBullets(text) {
  if (!text) return null
  const lower = text.toLowerCase()
  if (lower.includes('i cannot answer this from the provided papers')) {
    return { type: 'refusal' }
  }
  const lines = text.split('\n').filter((l) => l.trim())
  const bullets = lines.map((line) => {
    const content = line.replace(/^[-•*]\s*/, '').trim()
    const citationPattern = /\[(?:Citations:\s*)?Paper\s+\d+\]/g
    const matches = content.match(citationPattern) || []
    const unique = [...new Set(matches)]
    const cleanedText = content.replace(citationPattern, '').replace(/\s{2,}/g, ' ').trim()
    return { text: cleanedText, cite: unique.length ? unique[0] : null }
  })
  return { type: 'bullets', bullets }
}

// ---------------------------------------------------------------------------
// Single message bubble
// ---------------------------------------------------------------------------
function ChatMessage({ msg }) {
  if (msg.isLoading) {
    return (
      <div className="msg msg--assistant">
        <div className="msg__avatar msg__avatar--bot">
          <BotIcon />
        </div>
        <div className="msg__body">
          <div className="typing-indicator">
            <span /><span /><span />
          </div>
        </div>
      </div>
    )
  }

  if (msg.role === 'user') {
    return (
      <div className="msg msg--user">
        <div className="msg__body msg__body--user">
          <p>{msg.content}</p>
        </div>
        <div className="msg__avatar msg__avatar--user">
          <UserIcon />
        </div>
      </div>
    )
  }

  // Assistant message
  const parsed = parseBullets(msg.content)

  return (
    <div className="msg msg--assistant">
      <div className="msg__avatar msg__avatar--bot">
        <BotIcon />
      </div>
      <div className="msg__body">
        {parsed?.type === 'refusal' ? (
          <p className="msg__refusal">
            I cannot answer this from the provided papers.
          </p>
        ) : parsed?.type === 'bullets' ? (
          <ul className="msg__bullets">
            {parsed.bullets.map((b, i) => (
              <li key={i}>
                <span>{b.text}</span>
                {b.cite && <cite className="msg__cite">{b.cite}</cite>}
              </li>
            ))}
          </ul>
        ) : (
          <p>{msg.content}</p>
        )}

        {/* Warnings */}
        {Array.isArray(msg.warnings) && msg.warnings.length > 0 && (
          <div className="msg__warnings">
            <span>⚠ {msg.warnings.join(' · ')}</span>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Empty state – shown before the first message
// ---------------------------------------------------------------------------
function EmptyState() {
  return (
    <div className="chat-empty">
      <h2 className="chat-empty__title">Cast AI<span className="brand-dot">.</span></h2>
      {/* <p className="chat-empty__sub">Ask me anything about disaster research and evidence from the indexed papers.</p> */}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Chat component
// ---------------------------------------------------------------------------
export default function Chat({ goldenQuestions = [], onEvaluated = null }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const bottomRef = useRef(null)
  const textareaRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleInputChange = (e) => {
    setInput(e.target.value)
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 180) + 'px'
    }
  }

  const sendMessage = useCallback(
    async (questionText) => {
      const q = (questionText !== undefined ? questionText : input).trim()
      if (!q || isLoading) return

      setInput('')
      if (textareaRef.current) textareaRef.current.style.height = 'auto'

      const userId = Date.now()
      const loadingId = Date.now() + 1

      setMessages((prev) => [
        ...prev,
        { id: userId, role: 'user', content: q },
        { id: loadingId, role: 'assistant', isLoading: true, content: '', citations: [], warnings: [] },
      ])
      setIsLoading(true)

      try {
        const res = await fetch(`${API_BASE}/api/ask`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question: q }),
        })

        if (!res.ok) throw new Error(String(res.status))
        const data = await res.json()

        setMessages((prev) =>
          prev.map((m) =>
            m.id === loadingId
              ? {
                  ...m,
                  isLoading: false,
                  content: data.answer || '',
                  citations: data.citations || [],
                  warnings: data.citation_warnings || [],
                }
              : m
          )
        )

        if (onEvaluated) {
          onEvaluated({ questionText: q, answer: data.answer || '', citations: data.citations || [] })
        }
      } catch (err) {
        const code = parseInt(err.message, 10)
        const errorContent =
          code === 429
            ? 'Too many requests – please wait a moment and try again.'
            : code >= 500
            ? 'The backend returned an error. Check server logs and retry.'
            : 'Could not reach the backend. Make sure it is running on port 8000.'

        setMessages((prev) =>
          prev.map((m) =>
            m.id === loadingId
              ? { ...m, isLoading: false, content: errorContent, citations: [], warnings: [] }
              : m
          )
        )
      } finally {
        setIsLoading(false)
      }
    },
    [input, isLoading, onEvaluated]
  )

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const isEmpty = messages.length === 0

  return (
    <div className="chat-root">
      {/* Header */}
      <div className="chat-topbar">
        <div className="chat-topbar__left">
          <span className="chat-topbar__title">Chat</span>
        </div>
        {!isEmpty && (
          <button className="chat-topbar__clear" onClick={() => setMessages([])}>
            New chat
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="chat-messages">
        {isEmpty ? (
          <EmptyState />
        ) : (
          <>
            {messages.map((msg) => (
              <ChatMessage key={msg.id} msg={msg} />
            ))}
            <div ref={bottomRef} style={{ height: 1 }} />
          </>
        )}
      </div>

      {/* Input */}
      <div className="chat-composer">
        <div className="chat-composer__inner">
          <textarea
            ref={textareaRef}
            className="chat-composer__input"
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask about wildfire governance, evacuations, or fire management…"
            rows={1}
            disabled={isLoading}
          />
          <button
            className="chat-composer__send"
            onClick={() => sendMessage()}
            disabled={!input.trim() || isLoading}
            aria-label="Send message"
          >
            <SendIcon />
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Icons (inline SVG – no extra deps)
// ---------------------------------------------------------------------------
function BotIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 2a2 2 0 0 1 2 2v2H10V4a2 2 0 0 1 2-2z"/>
      <rect x="3" y="6" width="18" height="14" rx="3"/>
      <circle cx="8.5" cy="12" r="1.5" fill="currentColor" stroke="none"/>
      <circle cx="15.5" cy="12" r="1.5" fill="currentColor" stroke="none"/>
      <path d="M9 16s1 1.5 3 1.5 3-1.5 3-1.5"/>
    </svg>
  )
}

function BotIconLarge() {
  return (
    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M12 2a2 2 0 0 1 2 2v2H10V4a2 2 0 0 1 2-2z"/>
      <rect x="3" y="6" width="18" height="14" rx="3"/>
      <circle cx="8.5" cy="12" r="1.5" fill="currentColor" stroke="none"/>
      <circle cx="15.5" cy="12" r="1.5" fill="currentColor" stroke="none"/>
      <path d="M9 16s1 1.5 3 1.5 3-1.5 3-1.5"/>
    </svg>
  )
}

function UserIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z"/>
    </svg>
  )
}

function SendIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13"/>
      <polygon points="22 2 15 22 11 13 2 9 22 2"/>
    </svg>
  )
}
