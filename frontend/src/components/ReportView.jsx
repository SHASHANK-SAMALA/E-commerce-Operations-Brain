const s = {
  wrap: { background: '#1e293b', borderRadius: '12px', padding: '20px' },
  title: { fontSize: '18px', fontWeight: 700, color: '#38bdf8', marginBottom: '4px' },
  score: (v) => ({ display: 'inline-block', padding: '3px 10px', borderRadius: '20px', fontSize: '12px', fontWeight: 700,
    background: v >= 0.8 ? '#166534' : v >= 0.6 ? '#854d0e' : '#7f1d1d',
    color: v >= 0.8 ? '#86efac' : v >= 0.6 ? '#fde047' : '#fca5a5' }),
  section: { marginTop: '20px' },
  sectionTitle: { fontSize: '11px', fontWeight: 700, color: '#cbd5e1', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '0.05em' },
  card: { background: '#0f172a', borderRadius: '8px', padding: '12px', marginBottom: '8px' },
  cardTitle: { fontSize: '13px', fontWeight: 700, color: '#f1f5f9', marginBottom: '4px' },
  text: { fontSize: '13px', color: '#94a3b8', lineHeight: 1.6 },
  badge: (t) => ({
    display: 'inline-block', padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600,
    background: t === 'CRITICAL' ? '#7f1d1d' : t === 'HIGH' ? '#431407' : '#1e3a5f',
    color: t === 'CRITICAL' ? '#fca5a5' : t === 'HIGH' ? '#fdba74' : '#93c5fd',
    marginRight: '6px',
  }),
  domain: { display: 'inline-block', padding: '2px 8px', background: '#1e293b', borderRadius: '4px', fontSize: '11px', color: '#64748b', marginRight: '4px', border: '1px solid #334155' },
}

export default function ReportView({ report }) {
  if (!report) return null
  const { summary = '', evidence_score = 0, root_causes = [], proposed_actions = [] } = report

  return (
    <div style={s.wrap}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={s.title}>Investigation Report</div>
        <span style={s.score(evidence_score)}>Evidence {(evidence_score * 100).toFixed(0)}%</span>
      </div>

      {summary && (
        <div style={{ marginTop: '12px', ...s.text, color: '#cbd5e1', lineHeight: 1.8 }}>{summary}</div>
      )}

      {root_causes.length > 0 && (
        <div style={s.section}>
          <div style={s.sectionTitle}>Root Causes ({root_causes.length})</div>
          {root_causes.map((rc, i) => (
            <div key={i} style={s.card}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                <span style={s.badge(rc.severity || 'MEDIUM')}>{rc.severity || 'MEDIUM'}</span>
                <span style={{ ...s.cardTitle, marginBottom: 0 }}>{rc.cause || rc}</span>
              </div>
              {rc.domains_implicated && (
                <div style={{ marginBottom: '4px' }}>
                  {rc.domains_implicated.map(d => <span key={d} style={s.domain}>{d}</span>)}
                </div>
              )}
              {rc.evidence && <div style={s.text}>{rc.evidence}</div>}
              {rc.recommended_action && (
                <div style={{ ...s.text, color: '#60a5fa', marginTop: '4px' }}>→ {rc.recommended_action}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {proposed_actions.length > 0 && (
        <div style={s.section}>
          <div style={s.sectionTitle}>Proposed Actions ({proposed_actions.length})</div>
          {proposed_actions.map((a, i) => (
            <div key={i} style={s.card}>
              <div style={s.cardTitle}>{(a.action_type || '').replace(/_/g, ' ')}</div>
              {a.description && <div style={s.text}>{a.description}</div>}
              {a.estimated_impact && <div style={{ ...s.text, color: '#4ade80', marginTop: '4px' }}>Impact: {a.estimated_impact}</div>}
              {a.historical_success_rate != null && (
                <div style={{ ...s.text, color: '#a78bfa', marginTop: '2px' }}>
                  Historical success: {(a.historical_success_rate * 100).toFixed(0)}%
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
