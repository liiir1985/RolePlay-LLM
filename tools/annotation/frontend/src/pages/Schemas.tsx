import { useState, useEffect } from 'react'
import { api } from '../api'

const FIELD_TYPES = ['number', 'category', 'text', 'boolean', 'score']
const FIELD_TYPE_LABELS: Record<string, string> = {
  number: '数字', category: '分类', text: '文本', boolean: '布尔', score: '1-10分'
}

function emptyField() {
  return { name: '', label: '', type: 'score', options: '', order_idx: 0 }
}

function SchemaModal({ schema, onClose, onSaved }: { schema: any; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(schema?.name || '')
  const [fields, setFields] = useState<any[]>(
    schema?.fields?.map((f: any) => ({ ...f, options: f.options?.join(',') || '' })) || [emptyField()]
  )
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  const setField = (i: number, key: string, val: any) =>
    setFields(fs => fs.map((f, idx) => idx === i ? { ...f, [key]: val } : f))

  const save = async () => {
    if (!name.trim()) { setErr('请填写模板名称'); return }
    setSaving(true)
    try {
      const payload = {
        name,
        fields: fields.map((f, i) => ({
          name: f.name, label: f.label, type: f.type,
          options: f.type === 'category' && f.options ? f.options.split(',').map((s: string) => s.trim()).filter(Boolean) : null,
          order_idx: i,
        })),
      }
      if (schema?.id) await api.updateSchema(schema.id, payload)
      else await api.createSchema(payload)
      onSaved()
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal">
        <h2>{schema ? '编辑评估模板' : '新建评估模板'}</h2>
        <div className="form-row">
          <label>模板名称</label>
          <input type="text" value={name} onChange={e => setName(e.target.value)} />
        </div>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>评估字段</div>
        {fields.map((f, i) => (
          <div key={i} className="card" style={{ padding: 12, marginBottom: 8 }}>
            <div className="flex">
              <div className="flex-1">
                <div className="form-row">
                  <label>字段 key</label>
                  <input type="text" value={f.name} onChange={e => setField(i, 'name', e.target.value)} placeholder="如 quality" />
                </div>
              </div>
              <div className="flex-1">
                <div className="form-row">
                  <label>显示标签</label>
                  <input type="text" value={f.label} onChange={e => setField(i, 'label', e.target.value)} placeholder="如 质量评分" />
                </div>
              </div>
              <div>
                <div className="form-row">
                  <label>类型</label>
                  <select value={f.type} onChange={e => setField(i, 'type', e.target.value)}>
                    {FIELD_TYPES.map(t => <option key={t} value={t}>{FIELD_TYPE_LABELS[t]}</option>)}
                  </select>
                </div>
              </div>
              <button className="btn-danger btn-sm" style={{ marginTop: 20 }} onClick={() => setFields(fs => fs.filter((_, idx) => idx !== i))}>删除</button>
            </div>
            {f.type === 'category' && (
              <div className="form-row">
                <label>选项（逗号分隔）</label>
                <input type="text" value={f.options} onChange={e => setField(i, 'options', e.target.value)} placeholder="好,中,差" />
              </div>
            )}
          </div>
        ))}
        <button className="btn-secondary btn-sm" onClick={() => setFields(fs => [...fs, emptyField()])}>+ 添加字段</button>
        {err && <div style={{ color: 'red', marginTop: 8 }}>{err}</div>}
        <div className="flex mt-4">
          <button className="btn-secondary" onClick={onClose}>取消</button>
          <button className="btn-primary" onClick={save} disabled={saving}>{saving ? '保存中...' : '保存'}</button>
        </div>
      </div>
    </div>
  )
}

export default function Schemas() {
  const [schemas, setSchemas] = useState<any[]>([])
  const [editing, setEditing] = useState<any>(null)
  const [showModal, setShowModal] = useState(false)

  const load = () => api.listSchemas().then(setSchemas)
  useEffect(() => { load() }, [])

  const del = async (id: number) => {
    if (!confirm('确认删除此模板？')) return
    await api.deleteSchema(id)
    load()
  }

  return (
    <div>
      <div className="flex" style={{ marginBottom: 20 }}>
        <div className="page-title" style={{ margin: 0, flex: 1 }}>评估模板</div>
        <button className="btn-primary" onClick={() => { setEditing(null); setShowModal(true) }}>+ 新建模板</button>
      </div>
      {schemas.length === 0 && <div className="empty card">暂无评估模板</div>}
      {schemas.map(s => (
        <div key={s.id} className="card">
          <div className="flex">
            <div className="flex-1">
              <strong>{s.name}</strong>
              <div style={{ marginTop: 4 }}>
                {/* fields not loaded in list, show id */}
                <span style={{ color: '#999', fontSize: 12 }}>ID: {s.id}</span>
              </div>
            </div>
            <button className="btn-secondary btn-sm" onClick={() => api.getSchema(s.id).then(full => { setEditing(full); setShowModal(true) })}>编辑</button>
            <button className="btn-danger btn-sm" onClick={() => del(s.id)}>删除</button>
          </div>
        </div>
      ))}
      {showModal && (
        <SchemaModal
          schema={editing}
          onClose={() => setShowModal(false)}
          onSaved={() => { setShowModal(false); load() }}
        />
      )}
    </div>
  )
}
