import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

function CreateQueueModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState('')
  const [schemaId, setSchemaId] = useState('')
  const [schemas, setSchemas] = useState<any[]>([])
  const [err, setErr] = useState('')

  useEffect(() => { api.listSchemas().then(setSchemas) }, [])

  const save = async () => {
    if (!name.trim() || !schemaId) { setErr('请填写名称并选择模板'); return }
    try {
      await api.createQueue({ name, schema_id: Number(schemaId) })
      onSaved()
    } catch (e: any) { setErr(e.message) }
  }

  return (
    <div className="modal-overlay">
      <div className="modal">
        <h2>新建评估队列</h2>
        <div className="form-row"><label>队列名称</label><input type="text" value={name} onChange={e => setName(e.target.value)} /></div>
        <div className="form-row">
          <label>评估模板</label>
          <select value={schemaId} onChange={e => setSchemaId(e.target.value)}>
            <option value="">-- 选择模板 --</option>
            {schemas.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        {err && <div style={{ color: 'red' }}>{err}</div>}
        <div className="flex mt-4">
          <button className="btn-secondary" onClick={onClose}>取消</button>
          <button className="btn-primary" onClick={save}>创建</button>
        </div>
      </div>
    </div>
  )
}

export default function Queues() {
  const [queues, setQueues] = useState<any[]>([])
  const [showModal, setShowModal] = useState(false)
  const navigate = useNavigate()

  const load = () => api.listQueues().then(setQueues)
  useEffect(() => { load() }, [])

  const del = async (id: number) => {
    if (!confirm('确认删除此队列？')) return
    await api.deleteQueue(id)
    load()
  }

  return (
    <div>
      <div className="flex" style={{ marginBottom: 20 }}>
        <div className="page-title" style={{ margin: 0, flex: 1 }}>评估队列</div>
        <button className="btn-primary" onClick={() => setShowModal(true)}>+ 新建队列</button>
      </div>
      {queues.length === 0 && <div className="empty card">暂无评估队列</div>}
      {queues.map(q => (
        <div key={q.id} className="card" style={{ cursor: 'pointer' }} onClick={() => navigate(`/queues/${q.id}`)}>
          <div className="flex">
            <div className="flex-1">
              <strong>{q.name}</strong>
              <div style={{ marginTop: 4, fontSize: 12, color: '#666' }}>
                模板：{q.schema_name} &nbsp;|&nbsp;
                共 {q.total_items} 条，已标注 {q.annotated_items} 条
              </div>
            </div>
            <button className="btn-danger btn-sm" onClick={e => { e.stopPropagation(); del(q.id) }}>删除</button>
          </div>
        </div>
      ))}
      {showModal && (
        <CreateQueueModal onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); load() }} />
      )}
    </div>
  )
}
