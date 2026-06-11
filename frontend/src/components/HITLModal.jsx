import { useState } from 'react'

const s = {
  overlay: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex',
    alignItems: 'center', justifyContent: 'center', zIndex: 1000,
  },
  wrap: { background: '#1e1e1e', borderRadius: '14px', padding: '24px', border: '1px solid #f59e0b', width: '480px', maxWidth: '90vw', maxHeight: '80vh', overflowY: 'auto' },
  title: { fontSize: '16px', fontWeight: 700, color: '#f59e0b', marginBottom: '4px' },
  sub: { fontSize: '12px', color: '#94a3b8', marginBottom: '16px' },
  summary: { background: '#0f172a', borderRadius: '8px', padding: '12px', fontSize: '13px', color: '#cbd5e1', marginBottom: '16px', lineHeight: 1.6 },
  actions: { display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '16px' },
  action: { background: '#0f172a', borderRadius: '8px', padding: '12px' },
  actionHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' },
  actionType: { fontSize: '13px', fontWeight: 600, color: '#38bdf8' },
  impact: { fontSize: '12px', color: '#4ade80' },
  dryRun: { fontSize: '12px', color: '#94a3b8', fontStyle: 'italic', marginTop: '4px' },
  kadb: { fontSize: '11px', color: '#a78bfa', marginTop: '2px' },
  checkbox: { display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' },
  buttons: { display: 'flex', gap: '10px', marginTop: '8px' },
  btn: (v) => ({
    flex: 1, padding: '10px', borderRadius: '8px', border: 'none', cursor: 'pointer',
    fontWeight: 700, fontSize: '14px',
    background: v === 'approve' ? '#16a34a' : '#dc2626', color: '#fff',
  }),
  textarea: { width: '100%', background: '#0f172a', border: '1px solid #334155', borderRadius: '6px', color: '#e2e8f0', padding: '8px', fontSize: '12px', resize: 'none', marginTop: '8px' },
}

export default function HITLModal({ data, onDecide }) {
  const { proposed_actions = [], root_cause_summary = '' } = data
  const [selected, setSelected] = useState(() => new Set(proposed_actions.map(a => a.action_id)))
  const [showReject, setShowReject] = useState(false)
  const [rejectReason, setRejectReason] = useState('')

  const toggle = (id) => {
    setSelected(prev => {
      const s = new Set(prev)
      s.has(id) ? s.delete(id) : s.add(id)
      return s
    })
  }

  const approve = () => {
    onDecide({ approved: true, approved_action_ids: [...selected] })
  }

  const reject = () => {
    onDecide({ approved: false, rejection_reason: rejectReason || 'Rejected by user' })
  }

  return (
    <div style={s.overlay}>
    <div style={s.wrap}>
      <div style={s.title}>⏸ Human Approval Required</div>
      <div style={s.sub}>Review proposed actions before execution. Uncheck to exclude individual actions.</div>

      {root_cause_summary && (
        <div style={s.summary}><strong>Root cause:</strong> {root_cause_summary}</div>
      )}

      <div style={s.actions}>
        {proposed_actions.map(action => (
          <div key={action.action_id} style={s.action}>
            <div style={s.actionHeader}>
              <label style={s.checkbox}>
                <input type="checkbox" checked={selected.has(action.action_id)}
                  onChange={() => toggle(action.action_id)} />
                <span style={s.actionType}>{action.action_type.replace(/_/g, ' ')}</span>
              </label>
              {action.estimated_impact && <span style={s.impact}>{action.estimated_impact}</span>}
            </div>
            {action.dry_run_result && (
              <div style={s.dryRun}>Dry run: {
                typeof action.dry_run_result === 'string'
                  ? JSON.parse(action.dry_run_result)?.message || action.dry_run_result
                  : JSON.stringify(action.dry_run_result)
              }</div>
            )}
            {action.kadb_success_rate != null && (
              <div style={s.kadb}>Historical success rate: {(action.kadb_success_rate * 100).toFixed(0)}%</div>
            )}
          </div>
        ))}
      </div>

      {showReject && (
        <textarea
          style={s.textarea}
          rows={2}
          placeholder="Rejection reason (optional)"
          value={rejectReason}
          onChange={e => setRejectReason(e.target.value)}
        />
      )}

      <div style={s.buttons}>
        <button style={s.btn('approve')} onClick={approve} disabled={selected.size === 0}>
          ✅ Approve {selected.size} Action{selected.size !== 1 ? 's' : ''}
        </button>
        <button style={s.btn('reject')} onClick={() => showReject ? reject() : setShowReject(true)}>
          {showReject ? '❌ Confirm Reject' : '❌ Reject'}
        </button>
      </div>
    </div>
    </div>
  )
}
