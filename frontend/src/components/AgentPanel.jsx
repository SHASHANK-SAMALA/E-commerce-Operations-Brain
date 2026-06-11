const s = {
  panel: {
    width: '340px',
    background: '#171717',
    borderLeft: '1px solid #2d2d2d',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    flexShrink: 0,
  },
  header: {
    padding: '14px 16px',
    borderBottom: '1px solid #2d2d2d',
    fontSize: '11px',
    fontWeight: 700,
    color: '#555',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    flexShrink: 0,
  },
  content: { flex: 1, overflowY: 'auto', padding: '12px' },
  meta: {
    background: '#1e1e1e',
    borderRadius: '8px',
    padding: '10px 12px',
    marginBottom: '12px',
  },
  metaLabel: { color: '#555', fontSize: '10px', marginBottom: '2px', textTransform: 'uppercase', letterSpacing: '0.05em' },
  metaValue: { color: '#ececec', fontFamily: 'monospace', fontSize: '11px', wordBreak: 'break-all' },
  sectionTitle: {
    fontSize: '10px',
    fontWeight: 700,
    color: '#555',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    margin: '14px 0 8px',
  },
  traceEntry: { display: 'flex', gap: '8px', marginBottom: '7px', fontSize: '12px', alignItems: 'flex-start' },
  dot: (event) => ({
    width: '7px',
    height: '7px',
    borderRadius: '50%',
    marginTop: '3px',
    flexShrink: 0,
    background:
      event === 'blocked' || event === 'failed' ? '#ef4444'
      : event === 'completed' ? '#22c55e'
      : '#3b82f6',
  }),
  nodeName: { color: '#60a5fa', fontWeight: 600 },
  eventName: { color: '#666' },
  reportCard: { background: '#1e1e1e', borderRadius: '8px', padding: '12px', marginBottom: '8px' },
  scoreChip: (v) => ({
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: '20px',
    fontSize: '10px',
    fontWeight: 700,
    background: v >= 0.8 ? '#166534' : v >= 0.6 ? '#854d0e' : '#7f1d1d',
    color: v >= 0.8 ? '#86efac' : v >= 0.6 ? '#fde047' : '#fca5a5',
  }),
  summaryText: { fontSize: '12px', color: '#a0a0a0', lineHeight: 1.6, marginTop: '8px' },
  causeCard: { background: '#111', borderRadius: '6px', padding: '8px 10px', marginBottom: '6px' },
  causeName: { fontSize: '12px', fontWeight: 600, color: '#f1f5f9' },
  causeDetail: { fontSize: '11px', color: '#666', lineHeight: 1.5, marginTop: '2px' },
  badge: (t) => ({
    display: 'inline-block',
    padding: '1px 6px',
    borderRadius: '4px',
    fontSize: '10px',
    fontWeight: 700,
    marginRight: '6px',
    background: t === 'CRITICAL' ? '#7f1d1d' : t === 'HIGH' ? '#431407' : '#1e3a5f',
    color: t === 'CRITICAL' ? '#fca5a5' : t === 'HIGH' ? '#fdba74' : '#93c5fd',
  }),
  actionCard: { background: '#111', borderRadius: '6px', padding: '8px 10px', marginBottom: '6px' },
  actionType: { fontSize: '12px', color: '#38bdf8', fontWeight: 600, marginBottom: '2px' },
  actionDesc: { fontSize: '11px', color: '#666', lineHeight: 1.5 },
  actionImpact: { fontSize: '11px', color: '#4ade80', marginTop: '2px' },
}

export default function AgentPanel({ auditLog = [], investigation, report }) {
  const empty = !investigation && auditLog.length === 0 && !report

  return (
    <div style={s.panel}>
      <div style={s.header}>Agent Breakdown</div>
      <div style={s.content}>
        {empty ? (
          <div style={{ color: '#3a3a3a', fontSize: '12px', textAlign: 'center', marginTop: '50px', lineHeight: 2 }}>
            Investigation trace and<br />findings will appear here.
          </div>
        ) : (
          <>
            {investigation && (
              <div style={s.meta}>
                <div style={s.metaLabel}>Investigation ID</div>
                <div style={s.metaValue}>{investigation.query_id}</div>
                <div style={{ ...s.metaLabel, marginTop: '8px' }}>Status</div>
                <div style={{
                  ...s.metaValue,
                  color: investigation.status === 'completed' ? '#4ade80'
                    : investigation.status === 'error' ? '#f87171'
                    : '#fde047',
                }}>
                  {investigation.status}
                </div>
              </div>
            )}

            {auditLog.length > 0 && (
              <>
                <div style={s.sectionTitle}>Execution trace</div>
                {auditLog.map((entry, i) => (
                  <div key={i} style={s.traceEntry}>
                    <div style={s.dot(entry.event)} />
                    <div>
                      <span style={s.nodeName}>{entry.node}</span>
                      <span style={{ color: '#333' }}> › </span>
                      <span style={s.eventName}>{entry.event}</span>
                      {entry.error && (
                        <div style={{ color: '#f87171', fontSize: '10px', marginTop: '1px' }}>{entry.error}</div>
                      )}
                    </div>
                  </div>
                ))}
              </>
            )}

            {report && (
              <>
                <div style={s.sectionTitle}>Report</div>
                <div style={s.reportCard}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '12px', fontWeight: 700, color: '#ececec' }}>Investigation Report</span>
                    <span style={s.scoreChip(report.evidence_score || 0)}>
                      {((report.evidence_score || 0) * 100).toFixed(0)}% evidence
                    </span>
                  </div>
                  {report.summary && <div style={s.summaryText}>{report.summary}</div>}
                </div>

                {(report.root_causes || []).length > 0 && (
                  <>
                    <div style={s.sectionTitle}>Root causes ({report.root_causes.length})</div>
                    {report.root_causes.map((rc, i) => (
                      <div key={i} style={s.causeCard}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '3px' }}>
                          <span style={s.badge(rc.severity || 'MEDIUM')}>{rc.severity || 'MEDIUM'}</span>
                          <span style={s.causeName}>{rc.cause || String(rc)}</span>
                        </div>
                        {rc.evidence && <div style={s.causeDetail}>{rc.evidence}</div>}
                        {rc.recommended_action && (
                          <div style={{ ...s.causeDetail, color: '#60a5fa', marginTop: '3px' }}>
                            → {rc.recommended_action}
                          </div>
                        )}
                      </div>
                    ))}
                  </>
                )}

                {(report.proposed_actions || []).length > 0 && (
                  <>
                    <div style={s.sectionTitle}>Proposed actions ({report.proposed_actions.length})</div>
                    {report.proposed_actions.map((a, i) => (
                      <div key={i} style={s.actionCard}>
                        <div style={s.actionType}>{(a.action_type || '').replace(/_/g, ' ')}</div>
                        {a.description && <div style={s.actionDesc}>{a.description}</div>}
                        {a.estimated_impact && <div style={s.actionImpact}>{a.estimated_impact}</div>}
                        {a.historical_success_rate != null && (
                          <div style={{ ...s.actionDesc, color: '#a78bfa', marginTop: '2px' }}>
                            Historical success: {(a.historical_success_rate * 100).toFixed(0)}%
                          </div>
                        )}
                      </div>
                    ))}
                  </>
                )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
