import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../api'
import JsonViewer from '../components/JsonViewer'

function AnnotationField({ field, value, onChange }: { field: any; value: any; onChange: (v: any) => void }) {
  if (field.type === 'boolean') {
    return (
      <label className="flex" style={{ gap: 8, cursor: 'pointer' }}>
        <input type="checkbox" checked={!!value} onChange={e => onChange(e.target.checked)} style={{ width: 'auto' }} />
        <span>{field.label}</span>
      </label>
    )
  }
  if (field.type === 'score') {
    const v = value ?? 5
    return (
      <div>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>{field.label}</div>
        <div className="score-field">
          <input type="range" min={1} max={10} value={v} onChange={e => onChange(Number(e.target.value))} />
          <span className="score-value">{v}</span>
        </div>
      </div>
    )
  }
  if (field.type === 'number') {
    return (
      <div>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>{field.label}</div>
        <input type="number" value={value ?? ''} onChange={e => onChange(e.target.value === '' ? null : Number(e.target.value))} />
      </div>
    )
  }
  if (field.type === 'category') {
    return (
      <div>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>{field.label}</div>
        <select value={value ?? ''} onChange={e => onChange(e.target.value)}>
          <option value="">-- 选择 --</option>
          {(field.options || []).map((o: string) => <option key={o} value={o}>{o}</option>)}
        </select>
      </div>
    )
  }
  return (
    <div>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{field.label}</div>
      <textarea value={value ?? ''} onChange={e => onChange(e.target.value)} />
    </div>
  )
}

function parseJson(str: string | null): unknown {
  if (!str) return null
  try { return JSON.parse(str) } catch { return str }
}

export default function QueueItemDetail() {
  const { queueId, itemId } = useParams<{ queueId: string; itemId: string }>()
  const qid = Number(queueId)
  const iid = Number(itemId)
  const navigate = useNavigate()
  const [queue, setQueue] = useState<any>(null)
  const [item, setItem] = useState<any>(null)
  const [values, setValues] = useState<Record<string, any>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [allItemIds, setAllItemIds] = useState<number[]>([])

  const loadItem = useCallback((id: number) => {
    setItem(null)
    setSaved(false)
    api.getQueueItem(qid, id).then(data => {
      setItem(data)
      setValues(data.annotation || {})
    })
  }, [qid])

  useEffect(() => {
    api.getQueue(qid).then(setQueue)
    api.getQueueItemIds(qid).then(setAllItemIds)
  }, [qid])

  useEffect(() => { loadItem(iid) }, [iid, loadItem])

  const currentIndex = allItemIds.indexOf(iid)
  const prevId = currentIndex > 0 ? allItemIds[currentIndex - 1] : null
  const nextId = currentIndex < allItemIds.length - 1 ? allItemIds[currentIndex + 1] : null
  const goTo = (id: number) => navigate(`/queues/${qid}/items/${id}`, { replace: true })

  const save = async () => {
    setSaving(true)
    try {
      await api.annotateItem(qid, iid, values)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally { setSaving(false) }
  }

  const saveAndNext = async () => {
    setSaving(true)
    try {
      await api.annotateItem(qid, iid, values)
      if (nextId !== null) goTo(nextId)
    } finally { setSaving(false) }
  }

  if (!item || !queue) return <div>加载中...</div>

  return (
    <div>
      <div className="flex" style={{ marginBottom: 16 }}>
        <button className="btn-secondary btn-sm" onClick={() => navigate(`/queues/${qid}`)}>← 返回队列</button>
        <div style={{ flex: 1, marginLeft: 12, fontWeight: 600 }}>{item.record_name}</div>
        <span style={{ fontSize: 12, color: '#999', marginRight: 8 }}>
          {currentIndex >= 0 ? `${currentIndex + 1} / ${allItemIds.length}` : ''}
        </span>
        <span className={`badge badge-${item.status}`}>{item.status === 'annotated' ? '已标注' : '待标注'}</span>
      </div>
      <div className="flex" style={{ marginBottom: 12, gap: 8 }}>
        <button className="btn-secondary btn-sm" onClick={() => prevId !== null && goTo(prevId)} disabled={prevId === null}>← 上一条</button>
        <button className="btn-secondary btn-sm" onClick={() => nextId !== null && goTo(nextId)} disabled={nextId === null}>下一条 →</button>
      </div>
      <div className="split-view">
        <div className="split-panel">
          <div className="card">
            <details>
              <summary>完整信息（Raw）</summary>
              <div style={{ marginTop: 8 }}><JsonViewer data={item} initialExpanded={1} /></div>
            </details>
          </div>
          <div className="card">
            <details open>
              <summary>Input</summary>
              <div style={{ marginTop: 8 }}><JsonViewer data={parseJson(item.input)} initialExpanded={3} /></div>
            </details>
          </div>
          <div className="card">
            <details open>
              <summary>Output</summary>
              <div style={{ marginTop: 8 }}><JsonViewer data={parseJson(item.output)} initialExpanded={3} /></div>
            </details>
          </div>
        </div>
        <div className="split-panel">
          <div className="card">
            <div style={{ fontWeight: 700, marginBottom: 16, fontSize: 15 }}>评估字段</div>
            {queue.fields.map((f: any) => (
              <div key={f.id} className="form-row">
                <AnnotationField field={f} value={values[f.name]} onChange={v => setValues(prev => ({ ...prev, [f.name]: v }))} />
              </div>
            ))}
            <div className="flex mt-4" style={{ gap: 8 }}>
              <button className="btn-primary" onClick={save} disabled={saving}>{saving ? '保存中...' : '保存'}</button>
              <button className="btn-primary" onClick={saveAndNext} disabled={saving || nextId === null}>保存并下一条 →</button>
              {saved && <span style={{ color: 'green', fontSize: 13 }}>✓ 已保存</span>}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
