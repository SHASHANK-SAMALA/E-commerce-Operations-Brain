import { useState, useRef, useEffect } from 'react'

const s = {
  wrap: { display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' },
  messages: { flex: 1, overflowY: 'auto', padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' },
  msg: (role) => ({
    maxWidth: '90%',
    alignSelf: role === 'user' ? 'flex-end' : 'flex-start',
    background: role === 'user' ? '#1d4ed8' : role === 'error' ? '#7f1d1d' : '#1e293b',
    color: role === 'error' ? '#fca5a5' : '#e2e8f0',
    padding: '8px 12px',
    borderRadius: '10px',
    fontSize: '13px',
    lineHeight: 1.5,
  }),
  ts: { fontSize: '10px', color: '#475569', marginTop: '2px' },
  inputWrap: { padding: '12px', borderTop: '1px solid #1e293b', display: 'flex', flexDirection: 'column', gap: '8px' },
  textarea: { width: '100%', background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#e2e8f0', padding: '10px', fontSize: '13px', resize: 'none', outline: 'none' },
  row: { display: 'flex', gap: '8px' },
  btn: (variant) => ({
    flex: variant === 'primary' ? 1 : 'none',
    padding: '8px 14px',
    borderRadius: '6px',
    border: 'none',
    cursor: 'pointer',
    fontSize: '13px',
    fontWeight: 600,
    background: variant === 'primary' ? '#2563eb' : variant === 'audio' ? '#0f766e' : '#374151',
    color: '#fff',
  }),
  loader: { display: 'flex', gap: '4px', padding: '8px 12px', background: '#1e293b', borderRadius: '10px', alignSelf: 'flex-start' },
  dot: (i) => ({ width: '6px', height: '6px', borderRadius: '50%', background: '#38bdf8', animation: `bounce 1s ${i * 0.15}s infinite` }),
}

function Loader() {
  return (
    <div style={s.loader}>
      {[0, 1, 2].map(i => <div key={i} style={s.dot(i)} />)}
      <style>{`@keyframes bounce { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-6px)} }`}</style>
    </div>
  )
}

export default function ChatPanel({ messages, loading, onQuery, onAudio, onExport }) {
  const [text, setText] = useState('')
  const [recording, setRecording] = useState(false)
  const bottomRef = useRef(null)
  const mediaRef = useRef(null)
  const chunksRef = useRef([])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading])

  const send = () => {
    const q = text.trim()
    if (!q) return
    setText('')
    onQuery(q)
  }

  const toggleRecord = async () => {
    if (recording) {
      mediaRef.current?.stop()
      setRecording(false)
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const rec = new MediaRecorder(stream)
      chunksRef.current = []
      rec.ondataavailable = e => chunksRef.current.push(e.data)
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        stream.getTracks().forEach(t => t.stop())
        onAudio(blob)
      }
      rec.start()
      mediaRef.current = rec
      setRecording(true)
    } catch { alert('Microphone access denied') }
  }

  const EXAMPLES = [
    'Why did sales drop yesterday?',
    'Which products are out of stock?',
    'Show me paused campaigns',
    'Summarize business health',
  ]

  return (
    <div style={s.wrap}>
      <div style={s.messages}>
        {messages.length === 0 && (
          <div style={{ color: '#475569', fontSize: '12px', textAlign: 'center', padding: '20px 0' }}>
            <div style={{ marginBottom: '12px' }}>Quick starts:</div>
            {EXAMPLES.map(ex => (
              <div key={ex} onClick={() => onQuery(ex)}
                style={{ cursor: 'pointer', padding: '6px 10px', margin: '4px 0', background: '#1e293b', borderRadius: '6px', color: '#94a3b8', fontSize: '12px' }}>
                {ex}
              </div>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{ alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '90%' }}>
            <div style={s.msg(m.role)}>{m.content}</div>
            <div style={{ ...s.ts, textAlign: m.role === 'user' ? 'right' : 'left' }}>
              {new Date(m.ts).toLocaleTimeString()}
            </div>
          </div>
        ))}
        {loading && <Loader />}
        <div ref={bottomRef} />
      </div>
      <div style={s.inputWrap}>
        <textarea
          style={s.textarea}
          rows={3}
          placeholder="Ask a business question..."
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
        />
        <div style={s.row}>
          <button style={s.btn('primary')} onClick={send} disabled={loading}>
            {loading ? 'Investigating...' : 'Investigate →'}
          </button>
          <button style={{ ...s.btn('audio'), background: recording ? '#dc2626' : '#0f766e' }} onClick={toggleRecord}>
            {recording ? '⏹ Stop' : '🎤'}
          </button>
          <button style={s.btn('export')} onClick={onExport} title="Export CSV">⬇️</button>
        </div>
      </div>
    </div>
  )
}
