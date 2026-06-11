const s = {
  wrap: { padding: '16px', height: '100%' },
  title: { fontSize: '12px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '12px' },
  entry: { display: 'flex', gap: '8px', marginBottom: '10px', fontSize: '12px' },
  dot: (event) => ({ width: '8px', height: '8px', borderRadius: '50%', marginTop: '3px', flexShrink: 0,
    background: event === 'blocked' || event === 'failed' ? '#ef4444' : event === 'completed' ? '#22c55e' : '#3b82f6' }),
  node: { color: '#38bdf8', fontWeight: 600 },
  event: { color: '#94a3b8' },
  meta: { paragraph: '16px', background: '#0f172a', borderRadius: '8px', padding: '12px', marginBottom: '12px' },
  key: { color: '#64748b', fontSize: '11px' },
  val: { color: '#e2e8f0', fontSize: '12px' },
}

export default function TracePanel({ auditLog = [], investigation }) {
  return (
    <div style={s.wrap}>
      <div style={s.title}>Execution Trace</div>

      {investigation && (
        <div style={s.meta}>
          <div style={s.key}>Investigation ID</div>
          <div style={{ ...s.val, fontFamily: 'monospace', wordBreak: 'break-all' }}>{investigation.query_id}</div>
          <div style={{ ...s.key, marginTop: '8px' }}>Status</div>
          <div style={s.val}>{investigation.status}</div>
        </div>
      )}

      {auditLog.length === 0 ? (
        <div style={{ color: '#334155', fontSize: '12px', textAlign: 'center', marginTop: '20px' }}>
          Trace events will appear here during investigation
        </div>
      ) : (
        auditLog.map((entry, i) => (
          <div key={i} style={s.entry}>
            <div style={s.dot(entry.event)} />
            <div>
              <span style={s.node}>{entry.node}</span>
              <span style={{ color: '#475569' }}> → </span>
              <span style={s.event}>{entry.event}</span>
              {entry.error && <div style={{ color: '#f87171', fontSize: '11px', marginTop: '2px' }}>{entry.error}</div>}
            </div>
          </div>
        ))
      )}
    </div>
  )
}
