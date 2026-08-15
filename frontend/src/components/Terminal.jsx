import { useEffect, useRef } from 'react'
import StructuredContent, { isStructuredText } from './StructuredContent'
import './Terminal.css'

const STATUS_LABELS = {
  checking: 'Connecting to J.A.R.V.I.S. backend…',
  'awaiting-click': 'Click Enable voice to start the microphone',
  unlocking: 'Enabling microphone and audio…',
  denied: 'Microphone blocked — click Enable voice to retry',
  connecting: 'Connecting to J.A.R.V.I.S. backend…',
  listening: 'Listening — speak, then pause briefly',
  transcribing: 'Transcribing your voice (Groq Whisper)…',
  thinking: 'Thinking & controlling your Mac…',
  speaking: 'Speaking (Edge ultra-realistic voice)…',
  unsupported: 'Voice capture not supported in this browser',
  offline: 'Backend offline — start Backend server',
  error: 'Voice pipeline error',
  idle: 'Voice interface stopped',
}

const ROLE_META = {
  assistant: { prompt: '◆', className: 'jarvis-terminal__line--assistant' },
  error: { prompt: '!', className: 'jarvis-terminal__line--error' },
}

export default function Terminal({ entries = [], status = 'connecting' }) {
  const scrollRef = useRef(null)
  const jarvisEntries = entries.filter(
    (entry) => entry.role === 'assistant' || entry.role === 'error',
  )

  useEffect(() => {
    const node = scrollRef.current
    if (!node) return
    node.scrollTop = node.scrollHeight
  }, [jarvisEntries, status])

  const statusLabel = STATUS_LABELS[status] ?? STATUS_LABELS.idle
  const isActive = ['listening', 'transcribing', 'thinking', 'speaking', 'responding'].includes(
    status,
  )

  return (
    <section className="jarvis-terminal" aria-label="J.A.R.V.I.S. terminal">
      <header className="jarvis-terminal__header">
        <div className="jarvis-terminal__title">
          <span className="jarvis-terminal__dot" data-active={isActive} />
          J.A.R.V.I.S. Terminal
        </div>
        <div className="jarvis-terminal__status" data-status={status}>
          {statusLabel}
        </div>
      </header>

      <div className="jarvis-terminal__body" ref={scrollRef}>
        {jarvisEntries.length === 0 && (
          <p className="jarvis-terminal__placeholder">
            ◆ J.A.R.V.I.S. replies appear here. Your voice is processed on the backend.
          </p>
        )}

        {jarvisEntries.map((entry) => {
          const meta = ROLE_META[entry.role] ?? ROLE_META.assistant
          return (
            <div
              key={entry.id}
              className={`jarvis-terminal__line ${meta.className}${entry.streaming ? ' jarvis-terminal__line--streaming' : ''}`}
            >
              <span className="jarvis-terminal__time">[{entry.time}]</span>
              <span className="jarvis-terminal__prompt">{meta.prompt}</span>
              <span className="jarvis-terminal__text">
                {entry.streaming ? '…' : (
                  isStructuredText(entry.text)
                    ? <StructuredContent text={entry.text} />
                    : entry.text
                )}
              </span>
              {entry.streaming && <span className="jarvis-terminal__cursor" aria-hidden />}
            </div>
          )
        })}
      </div>
    </section>
  )
}
