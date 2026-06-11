import { useState, useCallback, useRef } from 'react'
import Sidebar from './components/Sidebar.jsx'
import ChatArea from './components/ChatArea.jsx'

const API_KEY = import.meta.env.VITE_API_KEY || 'dev-key-change-in-production'
const BASE = '/api/v1'

const headers = () => ({ 'Content-Type': 'application/json', 'X-API-Key': API_KEY })

// Returns a structured object consumed by the AgentResult component in ChatArea
function buildCompletionPayload(data, elapsedMs) {
  const lines = []
  const score = data.result?.evidence_score
  return {
    type: 'agent_result',
    elapsedMs: elapsedMs ?? null,
    score: data.result?.evidence_score ?? null,
    domain_reports: data.domain_reports || {},
    result: data.result || null,
    execution_results: data.execution_results || [],
  }
}

function makeConv(id, title = 'New conversation') {
  return { id, title, messages: [], report: null, auditLog: [], investigation: null, hitlData: null, loading: false, createdAt: Date.now() }
}

export default function App() {
  const [conversations, setConversations] = useState([])
  const [activeId, setActiveId] = useState(null)
  const pollRefs = useRef({})
  const startTsRefs = useRef({})

  const updateConv = (id, patch) => {
    setConversations(prev =>
      prev.map(c => c.id === id ? { ...c, ...(typeof patch === 'function' ? patch(c) : patch) } : c)
    )
  }

  const addMsg = (id, role, content, extra = {}) => {
    updateConv(id, c => ({ messages: [...c.messages, { role, content, ts: Date.now(), ...extra }] }))
  }

  const stopPolling = (id) => {
    if (pollRefs.current[id]) { clearInterval(pollRefs.current[id]); delete pollRefs.current[id] }
  }

  const pollStatus = useCallback((convId, queryId) => {
    pollRefs.current[convId] = setInterval(async () => {
      try {
        const res = await fetch(`${BASE}/investigate/${queryId}/status`, { headers: headers() })
        const data = await res.json()

        if (data.audit_log) updateConv(convId, { auditLog: data.audit_log })

        if (data.status === 'pending_approval') {
          stopPolling(convId)
          updateConv(convId, { loading: false, hitlData: { queryId, ...data } })
          addMsg(convId, 'system', `Analysis complete — ${data.proposed_actions?.length || 0} action(s) require your approval below.`)
        } else if (data.status === 'completed') {
          stopPolling(convId)
          const elapsed = startTsRefs.current[convId] ? Date.now() - startTsRefs.current[convId] : null
          updateConv(convId, { loading: false, report: data.result || null })
          const payload = buildCompletionPayload(data, elapsed)
          addMsg(convId, 'assistant', payload)
        } else if (data.status === 'error' || data.status === 'blocked') {
          stopPolling(convId)
          updateConv(convId, { loading: false })
          addMsg(convId, 'error', data.error || 'Investigation failed.')
        }
      } catch { /* network blip — keep polling */ }
    }, 2500)
  }, [])

  const handleNewConv = useCallback(() => {
    const id = `conv-${Date.now()}`
    setConversations(prev => [makeConv(id), ...prev])
    setActiveId(id)
  }, [])

  const handleSelectConv = useCallback((id) => setActiveId(id), [])

  const handleQuery = useCallback(async (query) => {
    let convId = activeId

    if (!convId) {
      convId = `conv-${Date.now()}`
      setConversations(prev => [makeConv(convId, query.slice(0, 50)), ...prev])
      setActiveId(convId)
    } else {
      updateConv(convId, c => c.title === 'New conversation' ? { title: query.slice(0, 50) } : {})
    }

    stopPolling(convId)
    startTsRefs.current[convId] = Date.now()
    updateConv(convId, { loading: true, report: null, hitlData: null })
    addMsg(convId, 'user', query)

    try {
      const res = await fetch(`${BASE}/investigate/`, {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({ query }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Request failed')

      updateConv(convId, { investigation: data })
      addMsg(convId, 'system', 'Investigation started — running domain agents in parallel...')
      pollStatus(convId, data.query_id)
    } catch (e) {
      updateConv(convId, { loading: false })
      addMsg(convId, 'error', e.message)
    }
  }, [activeId, pollStatus])

  const handleAudioTranscribe = useCallback(async (audioBlob) => {
    const form = new FormData()
    form.append('file', audioBlob, 'recording.webm')
    try {
      const res = await fetch(`${BASE}/audio/transcribe`, {
        method: 'POST',
        headers: { 'X-API-Key': API_KEY },
        body: form,
      })
      const data = await res.json()
      if (!res.ok) {
        if (activeId) addMsg(activeId, 'error', data.detail || 'Audio transcription failed.')
        return
      }
      if (data.text) handleQuery(data.text)
    } catch {
      if (activeId) addMsg(activeId, 'error', 'Audio transcription failed.')
    }
  }, [handleQuery, activeId])

  const handleHITLDecision = useCallback(async (decision) => {
    const conv = conversations.find(c => c.id === activeId)
    if (!conv?.hitlData) return
    const { queryId } = conv.hitlData

    updateConv(activeId, { hitlData: null, loading: true })
    addMsg(activeId, 'user', decision.approved ? 'Approved — executing actions...' : `Rejected — ${decision.rejection_reason || 'no reason given'}`)

    try {
      const res = await fetch(`${BASE}/investigate/${queryId}/resume`, {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify(decision),
      })
      const data = await res.json()
      updateConv(activeId, { loading: false })
      addMsg(activeId, 'system', `Investigation resumed — status: ${data.status}`)
      if (decision.approved) pollStatus(activeId, queryId)
    } catch (e) {
      updateConv(activeId, { loading: false })
      addMsg(activeId, 'error', e.message)
    }
  }, [activeId, conversations, pollStatus])

  const handleExport = useCallback(async () => {
    const res = await fetch(`${BASE}/export/incidents`, { headers: headers() })
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'incidents.csv'; a.click()
    URL.revokeObjectURL(url)
  }, [])

  const active = conversations.find(c => c.id === activeId)

  return (
    <div style={{ display: 'flex', height: '100vh', background: '#212121', color: '#ececec', fontFamily: 'system-ui, -apple-system, sans-serif', overflow: 'hidden' }}>
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        auditLog={active?.auditLog || []}
        report={active?.report || null}
        investigation={active?.investigation || null}
        onNew={handleNewConv}
        onSelect={handleSelectConv}
      />
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <ChatArea
          messages={active?.messages || []}
          loading={active?.loading || false}
          hitlData={active?.hitlData || null}
          onQuery={handleQuery}
          onAudio={handleAudioTranscribe}
          onExport={handleExport}
          onHITLDecide={handleHITLDecision}
        />
      </div>
    </div>
  )
}
