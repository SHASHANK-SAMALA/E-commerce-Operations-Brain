import { useState, useRef, useEffect } from 'react'

const EXAMPLES = [
  'Why did sales drop yesterday?',
  'Which products are out of stock?',
  'Show me paused campaigns',
  'Summarize business health',
]

const s = {
  wrap: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    background: '#212121',
  },
  messages: {
    flex: 1,
    overflowY: 'auto',
    padding: '24px 0 8px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
  },
  msgRow: (role) => ({
    width: '100%',
    maxWidth: '760px',
    padding: '6px 24px',
    display: 'flex',
    justifyContent: role === 'user' ? 'flex-end' : 'flex-start',
    boxSizing: 'border-box',
  }),
  bubble: (role) => ({
    maxWidth: role === 'user' ? '72%' : '100%',
    background: role === 'user' ? '#2f2f2f' : 'transparent',
    color: role === 'error' ? '#f87171' : '#ececec',
    padding: role === 'user' ? '10px 14px' : '2px 0',
    borderRadius: role === 'user' ? '12px' : '0',
    fontSize: '14px',
    lineHeight: 1.7,
    fontStyle: role === 'system' ? 'italic' : 'normal',
    opacity: role === 'system' ? 0.65 : 1,
  }),
  timing: {
    fontSize: '11px',
    color: '#555',
    marginTop: '4px',
  },
  inputArea: {
    padding: '8px 24px 20px',
    display: 'flex',
    justifyContent: 'center',
    flexShrink: 0,
  },
  inputWrap: {
    width: '100%',
    maxWidth: '760px',
    background: '#2f2f2f',
    borderRadius: '14px',
    border: '1px solid #404040',
    display: 'flex',
    flexDirection: 'column',
  },
  textarea: {
    background: 'transparent',
    border: 'none',
    color: '#ececec',
    padding: '14px 16px 8px',
    fontSize: '14px',
    resize: 'none',
    outline: 'none',
    lineHeight: 1.6,
    fontFamily: 'inherit',
  },
  toolbar: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '4px 10px 10px',
  },
  iconBtn: (active) => ({
    padding: '6px 10px',
    borderRadius: '6px',
    border: 'none',
    cursor: 'pointer',
    fontSize: '12px',
    fontWeight: 500,
    background: active ? '#3a1a1a' : 'transparent',
    color: active ? '#f87171' : '#8e8ea0',
    display: 'flex',
    alignItems: 'center',
    gap: '5px',
  }),
  sendBtn: (disabled) => ({
    padding: '8px 18px',
    borderRadius: '8px',
    border: 'none',
    cursor: disabled ? 'not-allowed' : 'pointer',
    fontSize: '13px',
    fontWeight: 600,
    background: disabled ? '#3a3a3a' : '#10a37f',
    color: disabled ? '#555' : '#fff',
    transition: 'background 0.15s',
  }),
  welcome: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    flex: 1,
    gap: '28px',
    paddingBottom: '60px',
  },
  welcomeTitle: {
    fontSize: '26px',
    fontWeight: 600,
    color: '#ececec',
    textAlign: 'center',
  },
  exampleGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '10px',
    maxWidth: '540px',
    width: '100%',
    padding: '0 24px',
    boxSizing: 'border-box',
  },
  exampleCard: {
    background: '#2f2f2f',
    border: '1px solid #404040',
    borderRadius: '10px',
    padding: '12px 14px',
    cursor: 'pointer',
    fontSize: '13px',
    color: '#ececec',
    lineHeight: 1.5,
  },
  loaderRow: {
    display: 'flex',
    gap: '5px',
    padding: '10px 24px',
    maxWidth: '760px',
    width: '100%',
    boxSizing: 'border-box',
    alignItems: 'center',
  },
  dot: (i) => ({
    width: '7px',
    height: '7px',
    borderRadius: '50%',
    background: '#10a37f',
    animation: `bounce 1s ${i * 0.15}s infinite`,
  }),
  hitlCard: {
    background: '#1a2a1a',
    border: '1px solid #10a37f',
    borderRadius: '12px',
    padding: '18px',
    width: '100%',
  },
  hitlTitle: {
    fontWeight: 700,
    fontSize: '14px',
    color: '#10a37f',
    marginBottom: '12px',
  },
  hitlAction: {
    padding: '10px 0',
    borderBottom: '1px solid #2d2d2d',
    marginBottom: '8px',
  },
  hitlActionName: {
    fontWeight: 600,
    fontSize: '13px',
    color: '#ececec',
    marginBottom: '3px',
  },
  hitlActionMeta: {
    fontSize: '12px',
    color: '#8e8ea0',
    fontFamily: 'monospace',
  },
  hitlDryRun: {
    fontSize: '12px',
    color: '#a3e6cb',
    marginTop: '4px',
  },
  hitlSummary: {
    fontSize: '13px',
    color: '#8e8ea0',
    fontStyle: 'italic',
    marginBottom: '14px',
    lineHeight: 1.6,
  },
  hitlBtns: {
    display: 'flex',
    gap: '10px',
    marginTop: '14px',
  },
  approveBtn: {
    padding: '9px 20px',
    borderRadius: '8px',
    border: 'none',
    cursor: 'pointer',
    fontSize: '13px',
    fontWeight: 600,
    background: '#10a37f',
    color: '#fff',
  },
  rejectBtn: {
    padding: '9px 20px',
    borderRadius: '8px',
    cursor: 'pointer',
    fontSize: '13px',
    fontWeight: 600,
    background: 'transparent',
    border: '1px solid #f87171',
    color: '#f87171',
  },
}

function Loader({ label }) {
  return (
    <div style={s.loaderRow}>
      {[0, 1, 2].map(i => <div key={i} style={s.dot(i)} />)}
      {label && <span style={{ fontSize: '12px', color: '#555', marginLeft: '6px' }}>{label}</span>}
      <style>{`@keyframes bounce { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-6px)} }`}</style>
    </div>
  )
}

function HITLInline({ hitlData, onDecide }) {
  const actions = hitlData.proposed_actions || []
  return (
    <div style={s.msgRow('assistant')}>
      <div style={s.hitlCard}>
        <div style={s.hitlTitle}>
          Human Approval Required — {actions.length} action{actions.length !== 1 ? 's' : ''} proposed
        </div>
        {hitlData.root_cause_summary && (
          <div style={s.hitlSummary}>{hitlData.root_cause_summary}</div>
        )}
        {actions.map(a => (
          <div key={a.action_id} style={s.hitlAction}>
            <div style={s.hitlActionName}>{a.action_type}</div>
            <div style={s.hitlActionMeta}>{JSON.stringify(a.params)}</div>
            {a.estimated_impact && (
              <div style={{ fontSize: '12px', color: '#a3e6cb', marginTop: '3px' }}>
                Est. impact: {a.estimated_impact}
              </div>
            )}
            {a.dry_run_result && (
              <div style={s.hitlDryRun}>
                Dry run: {typeof a.dry_run_result === 'string'
                  ? a.dry_run_result.slice(0, 200)
                  : JSON.stringify(a.dry_run_result).slice(0, 200)}
              </div>
            )}
            {a.kadb_success_rate != null && (
              <div style={{ fontSize: '11px', color: '#555', marginTop: '3px' }}>
                Historical success rate: {(a.kadb_success_rate * 100).toFixed(0)}%
              </div>
            )}
          </div>
        ))}
        <div style={s.hitlBtns}>
          <button style={s.approveBtn} onClick={() => onDecide({ approved: true })}>
            Approve All
          </button>
          <button style={s.rejectBtn} onClick={() => onDecide({ approved: false, rejection_reason: 'User rejected' })}>
            Reject
          </button>
        </div>
      </div>
    </div>
  )
}

function formatElapsed(ms) {
  if (!ms) return null
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

// ── Formatting helpers ────────────────────────────────────────────────────────
// fPct: for 0–1 fraction values (e.g. sentiment_score)
function fPct(v) { return v != null ? `${(v * 100).toFixed(1)}%` : '—' }
// fSign: for delta_pct fields already stored as percentages (e.g. -9.59 means -9.59%)
function fSign(v) { return v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}%` }
function fMoney(v) { return v != null ? `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '—' }

// ── Shared sub-components ─────────────────────────────────────────────────────
function DataRow({ label, value }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '4px 0', borderBottom: '1px solid #1c1c1c' }}>
      <span style={{ color: '#666', fontSize: '12px', flexShrink: 0, paddingRight: '12px' }}>{label}</span>
      <span style={{ color: '#ececec', fontSize: '12px', textAlign: 'right' }}>{value}</span>
    </div>
  )
}

function BulletList({ items }) {
  if (!items?.length) return null
  return (
    <ul style={{ margin: '4px 0 0', padding: '0 0 0 14px', listStyle: 'disc' }}>
      {items.map((item, i) => (
        <li key={i} style={{ color: '#c8c8c8', fontSize: '12px', lineHeight: 1.65, paddingBottom: '1px' }}>{item}</li>
      ))}
    </ul>
  )
}

function SectionLabel({ text }) {
  return <div style={{ color: '#555', fontSize: '11px', marginTop: '10px', marginBottom: '3px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{text}</div>
}

// ── AgentCard — collapsible card for one agent ────────────────────────────────
function AgentCard({ title, summary, children }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{ background: '#1a1a1a', border: '1px solid #2a2a2a', borderRadius: '9px', marginBottom: '6px', overflow: 'hidden' }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', background: 'none', border: 'none', padding: '9px 12px',
          display: 'flex', alignItems: 'center', gap: '9px', cursor: 'pointer', textAlign: 'left',
        }}
      >
        {/* neutral dot — no per-agent colors */}
        <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#555', flexShrink: 0 }} />
        <span style={{ color: '#ececec', fontSize: '13px', fontWeight: 600, flexShrink: 0 }}>{title}</span>
        <span style={{
          color: '#666', fontSize: '12px', flex: 1,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{summary}</span>
        <span style={{ color: '#444', fontSize: '11px', flexShrink: 0, userSelect: 'none' }}>{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div style={{ padding: '2px 14px 12px 28px', borderTop: '1px solid #222' }}>
          {children}
        </div>
      )}
    </div>
  )
}

// ── AgentResult — renders the full structured investigation payload ────────────
function AgentResult({ payload }) {
  const { elapsedMs, score, domain_reports: dr = {}, result, execution_results: exec = [] } = payload
  const confPct = score != null ? fPct(score) : '?'
  const confLabel = score >= 0.8 ? 'HIGH' : score >= 0.5 ? 'MEDIUM' : 'LOW'
  const timing = elapsedMs != null ? ` · ${(elapsedMs / 1000).toFixed(1)}s` : ''

  const agentCards = []

  // Sales
  if (dr.sales_report) {
    const s = dr.sales_report
    const severity = s.anomaly_score >= 3 ? 'CRITICAL' : s.anomaly_score >= 2 ? 'SIGNIFICANT' : 'NORMAL'
    const summary = `Revenue ${fSign(s.revenue_delta_pct)} · Orders ${fSign(s.order_delta_pct)} · AOV ${fSign(s.aov_delta_pct)}${s.anomaly_score != null ? ` · Anomaly ${s.anomaly_score.toFixed(2)}` : ''}`
    agentCards.push(
      <AgentCard key="sales" title="Sales Agent" summary={summary}>
        <DataRow label="Revenue delta" value={fSign(s.revenue_delta_pct)} />
        <DataRow label="Order delta" value={fSign(s.order_delta_pct)} />
        <DataRow label="AOV delta" value={fSign(s.aov_delta_pct)} />
        {s.date_range && <DataRow label="Date range" value={s.date_range} />}
        {s.anomaly_score != null && <DataRow label="Anomaly score" value={`${s.anomaly_score.toFixed(2)} (${severity})`} />}
        <DataRow label="Significant drop" value={s.is_drop_significant ? 'YES' : 'NO'} />
        {s.raw_metrics?.total_revenue != null && <DataRow label="Total revenue" value={fMoney(s.raw_metrics.total_revenue)} />}
        {s.raw_metrics?.total_orders != null && <DataRow label="Total orders" value={s.raw_metrics.total_orders.toLocaleString()} />}
        {s.raw_metrics?.avg_aov != null && <DataRow label="Avg AOV" value={fMoney(s.raw_metrics.avg_aov)} />}
        {s.top_declining_categories?.length > 0 && (
          <><SectionLabel text="Declining categories" /><BulletList items={s.top_declining_categories} /></>
        )}
        {s.affected_regions?.length > 0 && <DataRow label="Affected regions" value={s.affected_regions.join(', ')} />}
      </AgentCard>
    )
  }

  // Inventory
  if (dr.inventory_report) {
    const inv = dr.inventory_report
    const n = inv.stockouts?.length || 0
    const summary = n > 0
      ? `${n} stockout${n !== 1 ? 's' : ''} · ${fMoney(inv.revenue_impact_estimate)} at risk · ${inv.restock_urgency || 'LOW'}`
      : `No stockouts · ${inv.restock_urgency || 'LOW'} urgency`
    agentCards.push(
      <AgentCard key="inventory" title="Inventory Agent" summary={summary}>
        <DataRow label="Restock urgency" value={inv.restock_urgency || 'LOW'} />
        <DataRow label="Cart abandonment spike" value={inv.cart_abandonment_spike ? 'YES' : 'NO'} />
        {inv.revenue_impact_estimate > 0 && <DataRow label="Revenue at risk" value={fMoney(inv.revenue_impact_estimate)} />}
        {inv.near_stockout_skus?.length > 0 && (
          <DataRow label={`Near stockout (${inv.near_stockout_skus.length})`} value={inv.near_stockout_skus.join(', ')} />
        )}
        {inv.stockouts?.length > 0 && (
          <>
            <SectionLabel text={`Stockouts (${inv.stockouts.length})`} />
            <BulletList items={inv.stockouts.map(item => {
              const hrs = item.time_oos_hours != null ? ` · OOS ${item.time_oos_hours.toFixed(0)}h` : ''
              const qty = item.suggested_restock_qty ? ` · restock ${item.suggested_restock_qty}` : ''
              return `${item.sku}${item.name ? ` (${item.name})` : ''}${hrs}${qty}`
            })} />
          </>
        )}
        {inv.top_affected_skus?.length > 0 && (
          <DataRow label="Top affected SKUs" value={inv.top_affected_skus.join(', ')} />
        )}
      </AgentCard>
    )
  }

  // Marketing
  if (dr.marketing_report) {
    const m = dr.marketing_report
    const p = m.paused_campaigns?.length || 0
    const summary = p > 0
      ? `${p} paused · ${fMoney(m.total_paused_spend)}/day · ROAS ${fSign(m.roas_delta_pct)}`
      : `All campaigns active · ROAS ${fSign(m.roas_delta_pct)}`
    agentCards.push(
      <AgentCard key="marketing" title="Marketing Agent" summary={summary}>
        {m.roas_delta_pct != null && <DataRow label="ROAS delta" value={fSign(m.roas_delta_pct)} />}
        {m.total_paused_spend > 0 && <DataRow label="Total paused spend" value={`${fMoney(m.total_paused_spend)}/day`} />}
        {m.paused_campaigns?.length > 0 && (
          <>
            <SectionLabel text={`Paused campaigns (${m.paused_campaigns.length})`} />
            <BulletList items={m.paused_campaigns.map(c => {
              const when = c.paused_at ? ` · paused ${new Date(c.paused_at).toLocaleDateString()}` : ''
              return `${c.name} [${c.channel}] · ${fMoney(c.daily_budget)}/day${when}`
            })} />
          </>
        )}
        {m.underperforming_channels?.length > 0 && (
          <DataRow label="Underperforming channels" value={m.underperforming_channels.join(', ')} />
        )}
        {m.missed_promotions?.length > 0 && (
          <DataRow label="Missed promotions" value={m.missed_promotions.join(', ')} />
        )}
      </AgentCard>
    )
  }

  // Support
  if (dr.support_report) {
    const sup = dr.support_report
    const trend = sup.sentiment_score < 0.35 ? 'DECLINING' : sup.sentiment_score < 0.6 ? 'NEUTRAL' : 'POSITIVE'
    const summary = `Spike: ${sup.complaint_spike ? `YES (${fSign(sup.complaint_delta_pct)})` : 'NO'} · Sentiment ${fPct(sup.sentiment_score)} ${trend}`
    agentCards.push(
      <AgentCard key="support" title="Support Agent" summary={summary}>
        <DataRow label="Complaint spike" value={sup.complaint_spike ? `YES (${fSign(sup.complaint_delta_pct)})` : 'NO'} />
        {sup.refund_rate_delta_pct != null && <DataRow label="Refund rate delta" value={fSign(sup.refund_rate_delta_pct)} />}
        {sup.sentiment_score != null && <DataRow label="Sentiment score" value={`${fPct(sup.sentiment_score)} (${trend})`} />}
        {sup.top_issues?.length > 0 && (
          <>
            <SectionLabel text="Top issues" />
            <BulletList items={sup.top_issues.map(issue => {
              const ex = issue.example_ticket ? ` — "${issue.example_ticket.slice(0, 70)}"` : ''
              return `${issue.issue_type} · ${issue.count} ticket${issue.count !== 1 ? 's' : ''}${ex}`
            })} />
          </>
        )}
        {sup.top_refund_skus?.length > 0 && (
          <DataRow label="Top refund SKUs" value={sup.top_refund_skus.join(', ')} />
        )}
      </AgentCard>
    )
  }

  return (
    <div style={{ width: '100%' }}>
      {/* Header line */}
      <div style={{ fontSize: '13px', color: '#ececec', marginBottom: '14px', lineHeight: 1.6 }}>
        Investigation complete — {confPct} evidence confidence ({confLabel}){timing}
      </div>

      {/* Agent cards */}
      {agentCards.length > 0 && (
        <div style={{ marginBottom: '10px' }}>
          <div style={{ fontSize: '11px', color: '#444', letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: '8px' }}>
            Agent findings — click to expand
          </div>
          {agentCards}
        </div>
      )}

      {/* Root cause synthesis */}
      {(result?.summary || result?.root_causes?.length > 0) && (
        <div style={{
          background: '#181818',
          border: '1px solid #2a2a2a',
          borderLeft: '2px solid #10a37f',
          borderRadius: '9px',
          padding: '12px 16px',
          marginBottom: '10px',
        }}>
          <div style={{ fontSize: '11px', color: '#10a37f', fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: '8px' }}>
            Root Cause Analysis
          </div>
          {result?.summary && (
            <div style={{ color: '#ececec', fontSize: '13px', lineHeight: 1.7, marginBottom: result?.root_causes?.length ? '12px' : 0 }}>
              {result.summary}
            </div>
          )}
          {result?.root_causes?.length > 0 && (
            <div>
              {result.root_causes.map((rc, i) => (
                <div key={i} style={{ padding: '6px 0', borderTop: i > 0 ? '1px solid #222' : 'none' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                    <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#555', flexShrink: 0, marginTop: '5px' }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '8px' }}>
                        <span style={{ color: '#ececec', fontSize: '13px' }}>{rc.cause}</span>
                        <span style={{ color: '#555', fontSize: '11px', flexShrink: 0 }}>{rc.domain} · {rc.confidence}</span>
                      </div>
                      {rc.evidence && (
                        <div style={{ color: '#666', fontSize: '12px', fontStyle: 'italic', lineHeight: 1.5, marginTop: '2px' }}>
                          {rc.evidence.slice(0, 160)}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Execution results */}
      {exec.length > 0 && (
        <div style={{ marginTop: '8px' }}>
          <div style={{ fontSize: '11px', color: '#444', letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: '6px' }}>
            Actions — {exec.filter(r => r.success).length}/{exec.length} succeeded
          </div>
          {exec.map((r, i) => (
            <div key={i} style={{ fontSize: '12px', color: r.success ? '#ececec' : '#f87171', padding: '2px 0' }}>
              {r.success ? '✓' : '✗'} {r.action_type}: {r.message || (r.success ? 'OK' : 'Failed')}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Render a single line — section headers (starting with ──) get special styling
function MsgLine({ line }) {
  if (line.startsWith('── ')) {
    return (
      <div style={{ color: '#10a37f', fontWeight: 700, fontSize: '12px', letterSpacing: '0.04em', marginTop: '12px', marginBottom: '4px', fontFamily: 'monospace' }}>
        {line}
      </div>
    )
  }
  if (line.startsWith('  • ')) {
    return <div style={{ color: '#c8c8c8', paddingLeft: '8px', fontSize: '13px' }}>{line}</div>
  }
  if (line.startsWith('    Evidence:')) {
    return <div style={{ color: '#666', paddingLeft: '16px', fontSize: '12px', fontStyle: 'italic' }}>{line}</div>
  }
  if (line.startsWith('  ✓')) {
    return <div style={{ color: '#10a37f', paddingLeft: '8px', fontSize: '13px' }}>{line}</div>
  }
  if (line.startsWith('  ✗')) {
    return <div style={{ color: '#f87171', paddingLeft: '8px', fontSize: '13px' }}>{line}</div>
  }
  return <div>{line}</div>
}
function TypedText({ content, animate }) {
  const [displayed, setDisplayed] = useState(animate ? '' : content)
  const idxRef = useRef(0)

  useEffect(() => {
    if (!animate) { setDisplayed(content); return }
    const words = content.split(' ')
    idxRef.current = 0
    setDisplayed('')
    const tick = () => {
      idxRef.current += 1
      setDisplayed(words.slice(0, idxRef.current).join(' '))
      if (idxRef.current < words.length) setTimeout(tick, 18)
    }
    setTimeout(tick, 18)
  }, [content, animate])

  return (
    <>
      {displayed.split('\n').map((line, j) =>
        line === '' ? <br key={j} /> : <MsgLine key={j} line={line} />
      )}
    </>
  )
}

export default function ChatArea({ messages, loading, hitlData, onQuery, onAudio, onExport, onHITLDecide }) {
  const [text, setText] = useState('')
  const [recording, setRecording] = useState(false)
  const bottomRef = useRef(null)
  // Track which message keys have already been animated so switching convs doesn't re-animate
  const animatedRef = useRef(new Set())

  const lastAssistantIdx = messages.reduce((last, m, i) => m.role === 'assistant' ? i : last, -1)
  const mediaRef = useRef(null)
  const chunksRef = useRef([])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading, hitlData])

  const send = () => {
    const q = text.trim()
    if (!q || loading) return
    setText('')
    onQuery(q)
  }

  const toggleRecord = async () => {
    if (recording) { mediaRef.current?.stop(); setRecording(false); return }
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

  const showWelcome = messages.length === 0 && !loading && !hitlData

  return (
    <div style={s.wrap}>
      <div style={s.messages}>
        {showWelcome ? (
          <div style={s.welcome}>
            <div style={s.welcomeTitle}>What would you like to investigate?</div>
            <div style={s.exampleGrid}>
              {EXAMPLES.map(ex => (
                <div key={ex} style={s.exampleCard} onClick={() => onQuery(ex)}>{ex}</div>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((m, i) => {
              const msgKey = `${m.ts}-${i}`
              const isLastAssistant = i === lastAssistantIdx && m.role === 'assistant'
              // Animate only the very first time this message renders
              const shouldAnimate = isLastAssistant && !animatedRef.current.has(msgKey)
              if (shouldAnimate) animatedRef.current.add(msgKey)

              return (
                <div key={i} style={s.msgRow(m.role)}>
                  <div style={s.bubble(m.role)}>
                    {m.content?.type === 'agent_result' ? (
                      <AgentResult payload={m.content} />
                    ) : shouldAnimate ? (
                      <TypedText content={String(m.content)} animate />
                    ) : (
                      String(m.content).split('\n').map((line, j) =>
                        line === '' ? <br key={j} /> : <MsgLine key={j} line={line} />
                      )
                    )}
                    {m.elapsed && (
                      <div style={s.timing}>{formatElapsed(m.elapsed)}</div>
                    )}
                  </div>
                </div>
              )
            })}
            {hitlData && <HITLInline hitlData={hitlData} onDecide={onHITLDecide} />}
            {loading && <Loader label="Investigating..." />}
            <div ref={bottomRef} />
          </>
        )}
      </div>

      <div style={s.inputArea}>
        <div style={s.inputWrap}>
          <textarea
            style={s.textarea}
            rows={3}
            placeholder="Ask a business question..."
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          />
          <div style={s.toolbar}>
            <div style={{ display: 'flex', gap: '4px' }}>
              <button
                style={s.iconBtn(recording)}
                onClick={toggleRecord}
                title={recording ? 'Stop recording' : 'Voice input'}
              >
                {recording ? '⏹ Stop' : '🎤 Voice'}
              </button>
              <button style={s.iconBtn(false)} onClick={onExport} title="Export incidents CSV">
                ⬇ Export
              </button>
            </div>
            <button style={s.sendBtn(loading || !text.trim())} onClick={send} disabled={loading || !text.trim()}>
              {loading ? 'Investigating...' : 'Send'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
