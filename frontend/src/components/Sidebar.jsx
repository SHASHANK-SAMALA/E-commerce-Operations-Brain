const s = {
  sidebar: {
    width: '280px',
    background: '#171717',
    display: 'flex',
    flexDirection: 'column',
    borderRight: '1px solid #2d2d2d',
    overflow: 'hidden',
    flexShrink: 0,
  },
  header: {
    padding: '16px 16px 12px',
    flexShrink: 0,
  },
  logo: { fontSize: '15px', fontWeight: 700, color: '#ececec', marginBottom: '2px' },
  logoSub: { fontSize: '11px', color: '#555', marginBottom: '12px' },
  newBtn: {
    width: '100%',
    padding: '9px 12px',
    background: 'transparent',
    border: '1px solid #3a3a3a',
    borderRadius: '8px',
    color: '#ececec',
    cursor: 'pointer',
    fontSize: '13px',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    boxSizing: 'border-box',
  },
  scrollArea: {
    flex: 1,
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    minHeight: 0,
  },
  section: {
    padding: '0 8px 4px',
  },
  sectionLabel: {
    fontSize: '10px',
    fontWeight: 700,
    color: '#444',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    padding: '10px 8px 4px',
  },
  convItem: (active) => ({
    padding: '8px 10px',
    borderRadius: '8px',
    cursor: 'pointer',
    fontSize: '13px',
    color: active ? '#ececec' : '#8e8ea0',
    background: active ? '#2f2f2f' : 'transparent',
    marginBottom: '1px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  }),
  emptyHint: {
    color: '#444',
    fontSize: '12px',
    padding: '20px 16px',
    textAlign: 'center',
    lineHeight: 1.8,
  },
  divider: {
    height: '1px',
    background: '#2d2d2d',
    margin: '8px 0',
    flexShrink: 0,
  },
  traceEntry: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '8px',
    padding: '4px 8px',
    fontSize: '12px',
  },
  traceDot: (status) => ({
    width: '7px',
    height: '7px',
    borderRadius: '50%',
    flexShrink: 0,
    marginTop: '4px',
    background: status === 'ok' ? '#10a37f' : status === 'fail' ? '#f87171' : status === 'running' ? '#facc15' : '#444',
  }),
  traceNode: { color: '#8e8ea0', fontWeight: 600, whiteSpace: 'nowrap' },
  traceEvent: { color: '#555', marginLeft: '2px' },
  evidenceBadge: (score) => ({
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: '999px',
    fontSize: '11px',
    fontWeight: 700,
    background: score >= 0.8 ? '#0d3d2d' : score >= 0.5 ? '#2d2800' : '#3a1a1a',
    color: score >= 0.8 ? '#10a37f' : score >= 0.5 ? '#facc15' : '#f87171',
    marginBottom: '8px',
  }),
  rootCause: {
    padding: '6px 10px',
    background: '#1e1e1e',
    borderRadius: '6px',
    borderLeft: '3px solid #10a37f',
    fontSize: '12px',
    color: '#c8c8c8',
    marginBottom: '6px',
    lineHeight: 1.5,
  },
  rootCauseConf: {
    fontSize: '10px',
    color: '#555',
    marginTop: '3px',
  },
  metaRow: {
    display: 'flex',
    justifyContent: 'space-between',
    fontSize: '11px',
    color: '#555',
    padding: '2px 8px',
    marginBottom: '4px',
  },
}

const OK_EVENTS = new Set(['report_generated', 'approved', 'executed', 'completed', 'done', 'skipped'])
const FAIL_EVENTS = new Set(['failed', 'rejected', 'blocked'])
const RUN_EVENTS = new Set(['started', 'running', 'pending'])

function dotStatus(entry) {
  if (FAIL_EVENTS.has(entry.event)) return 'fail'
  if (OK_EVENTS.has(entry.event)) return 'ok'
  if (RUN_EVENTS.has(entry.event)) return 'running'
  return 'neutral'
}

function groupConversations(conversations) {
  const now = Date.now()
  const DAY = 86400000
  const today = [], earlier = []
  for (const c of conversations) {
    const age = now - (c.createdAt || now)
    if (age < DAY) today.push(c)
    else earlier.push(c)
  }
  return { today, earlier }
}

export default function Sidebar({ conversations, activeId, auditLog, report, investigation, onNew, onSelect }) {
  const { today, earlier } = groupConversations(conversations)
  const hasTrace = auditLog && auditLog.length > 0
  const hasReport = report && (report.summary || report.root_causes?.length)
  const score = report?.evidence_score

  return (
    <div style={s.sidebar}>
      {/* Header */}
      <div style={s.header}>
        <div style={s.logo}>E-Commerce Brain</div>
        <div style={s.logoSub}>AI Operations Analyst</div>
        <button style={s.newBtn} onClick={onNew}>
          <span style={{ fontSize: '16px', lineHeight: 1 }}>+</span> New chat
        </button>
      </div>

      <div style={s.scrollArea}>
        {/* Conversations */}
        <div style={s.section}>
          {conversations.length === 0 ? (
            <div style={s.emptyHint}>No conversations yet.<br />Start one above.</div>
          ) : (
            <>
              {today.length > 0 && (
                <>
                  <div style={s.sectionLabel}>Today</div>
                  {today.map(c => (
                    <div key={c.id} style={s.convItem(c.id === activeId)} onClick={() => onSelect(c.id)} title={c.title}>
                      {c.title}
                    </div>
                  ))}
                </>
              )}
              {earlier.length > 0 && (
                <>
                  <div style={s.sectionLabel}>Earlier</div>
                  {earlier.map(c => (
                    <div key={c.id} style={s.convItem(c.id === activeId)} onClick={() => onSelect(c.id)} title={c.title}>
                      {c.title}
                    </div>
                  ))}
                </>
              )}
            </>
          )}
        </div>

        {/* Agent Activity */}
        {hasTrace && (
          <>
            <div style={s.divider} />
            <div style={s.sectionLabel}>Agent Activity</div>
            {investigation && (
              <div style={s.metaRow}>
                <span>ID: {investigation.query_id?.slice(0, 12)}…</span>
              </div>
            )}
            <div style={s.section}>
              {auditLog.map((entry, i) => (
                <div key={i} style={s.traceEntry}>
                  <div style={s.traceDot(dotStatus(entry))} />
                  <div>
                    <span style={s.traceNode}>{entry.node}</span>
                    <span style={s.traceEvent}> · {entry.event}</span>
                    {entry.error && (
                      <div style={{ fontSize: '11px', color: '#f87171', marginTop: '2px' }}>
                        {String(entry.error).slice(0, 80)}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Investigation Results */}
        {hasReport && (
          <>
            <div style={s.divider} />
            <div style={s.sectionLabel}>Investigation Results</div>
            <div style={{ padding: '4px 16px 8px' }}>
              {score != null && (
                <div style={s.evidenceBadge(score)}>
                  {(score * 100).toFixed(0)}% confidence
                </div>
              )}
              {report.summary && (
                <div style={{ fontSize: '12px', color: '#8e8ea0', marginBottom: '8px', lineHeight: 1.5 }}>
                  {report.summary.slice(0, 200)}{report.summary.length > 200 ? '…' : ''}
                </div>
              )}
              {report.root_causes?.slice(0, 4).map((rc, i) => (
                <div key={i} style={s.rootCause}>
                  {rc.cause}
                  {rc.confidence && <div style={s.rootCauseConf}>Confidence: {rc.confidence}</div>}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
