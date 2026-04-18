import { useState, useEffect } from 'react'
import { api } from '../api'

function AddRawModal({ datasetId, onClose, onSaved }: { datasetId: number; onClose: () => void; onSaved: () => void }) {
  const [records, setRecords] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const limit = 50

  const load = async () => {
    const data = await api.listRecords(page, limit, search, startTime, endTime)
    setRecords(data.items); setTotal(data.total)
  }
  useEffect(() => { load() }, [page, search, startTime, endTime])

  const toggle = (id: string) => setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const togglePage = () => {
    const ids = records.map(r => r.id)
    const all = ids.every(id => selected.has(id))
    setSelected(s => { const n = new Set(s); ids.forEach(id => all ? n.delete(id) : n.add(id)); return n })
  }

  const add = async () => {
    if (!selected.size) return
    const res = await api.addRawItems(datasetId, Array.from(selected))
    alert(`添加完成：新增 ${res.added} 条，重复跳过 ${res.duplicates} 条`)
    onSaved()
  }

  const totalPages = Math.ceil(total / limit)
  const pageAllChecked = records.length > 0 && records.every(r => selected.has(r.id))

  return (
    <div className="modal-overlay">
      <div className="modal" style={{ minWidth: 800, maxWidth: 900 }}>
        <h2>添加原始数据到数据集</h2>
        <div className="flex" style={{ marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
          <input type="text" placeholder="搜索 ID..." value={search} onChange={e => { setSearch(e.target.value); setPage(1) }} style={{ maxWidth: 200 }} />
          <label style={{ fontSize: 12, color: '#555', display: 'flex', alignItems: 'center', gap: 4 }}>
            从 <input type="datetime-local" value={startTime} onChange={e => { setStartTime(e.target.value); setPage(1) }} style={{ width: 'auto' }} />
          </label>
          <label style={{ fontSize: 12, color: '#555', display: 'flex', alignItems: 'center', gap: 4 }}>
            到 <input type="datetime-local" value={endTime} onChange={e => { setEndTime(e.target.value); setPage(1) }} style={{ width: 'auto' }} />
          </label>
          <span style={{ fontSize: 12, color: '#999', marginLeft: 'auto' }}>已选 {selected.size} / 共 {total} 条</span>
        </div>
        <table style={{ fontSize: 12 }}>
          <thead>
            <tr>
              <th style={{ width: 30 }}><input type="checkbox" checked={pageAllChecked} onChange={togglePage} style={{ width: 'auto' }} /></th>
              <th>ID</th><th>时间</th><th>Input (前100字)</th><th>Output (前100字)</th>
            </tr>
          </thead>
          <tbody>
            {records.map(r => (
              <tr key={r.id}>
                <td><input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} style={{ width: 'auto' }} /></td>
                <td style={{ fontFamily: 'monospace', fontSize: 11, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.id}</td>
                <td style={{ whiteSpace: 'nowrap', color: '#666' }}>{r.timestamp?.slice(0, 19).replace('T', ' ')}</td>
                <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.input_preview}</td>
                <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.output_preview}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {totalPages > 1 && (
          <div className="pagination">
            <button className="btn-secondary btn-sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>上一页</button>
            <span>{page}/{totalPages}</span>
            <button className="btn-secondary btn-sm" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}>下一页</button>
          </div>
        )}
        <div className="flex mt-4">
          <button className="btn-secondary" onClick={onClose}>取消</button>
          <button className="btn-primary" onClick={add} disabled={!selected.size}>添加 {selected.size} 条</button>
        </div>
      </div>
    </div>
  )
}

function AddAnnotatedModal({ datasetId, onClose, onSaved }: { datasetId: number; onClose: () => void; onSaved: () => void }) {
  const [queues, setQueues] = useState<any[]>([])
  const [selectedQueue, setSelectedQueue] = useState('')
  const [items, setItems] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const limit = 50

  useEffect(() => { api.listQueues().then(setQueues) }, [])

  const loadItems = async (qid: number, pg = 1) => {
    const data = await api.listQueueItems(qid, pg, limit, 'annotated')
    setItems(data.items); setTotal(data.total); setPage(pg)
  }

  const toggle = (id: number) => setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const togglePage = () => {
    const ids = items.map(i => i.id)
    const all = ids.every(id => selected.has(id))
    setSelected(s => { const n = new Set(s); ids.forEach(id => all ? n.delete(id) : n.add(id)); return n })
  }

  const add = async () => {
    if (!selected.size) return
    const res = await api.addAnnotatedItems(datasetId, Array.from(selected))
    alert(`添加完成：新增 ${res.added} 条，重复 ${res.duplicates} 条，跳过未标注 ${res.skipped} 条`)
    onSaved()
  }

  const totalPages = Math.ceil(total / limit)
  const pageAllChecked = items.length > 0 && items.every(i => selected.has(i.id))

  return (
    <div className="modal-overlay">
      <div className="modal" style={{ minWidth: 800, maxWidth: 900 }}>
        <h2>添加已标注数据到数据集</h2>
        <div className="form-row">
          <label>选择评估队列</label>
          <select value={selectedQueue} onChange={e => { setSelectedQueue(e.target.value); setSelected(new Set()); if (e.target.value) loadItems(Number(e.target.value)) }}>
            <option value="">-- 选择队列 --</option>
            {queues.map(q => <option key={q.id} value={q.id}>{q.name}（已标注 {q.annotated_items}）</option>)}
          </select>
        </div>
        {items.length > 0 && (
          <>
            <table style={{ fontSize: 12 }}>
              <thead>
                <tr>
                  <th style={{ width: 30 }}><input type="checkbox" checked={pageAllChecked} onChange={togglePage} style={{ width: 'auto' }} /></th>
                  <th>ID</th><th>时间</th><th>Input (前100字)</th><th>Output (前100字)</th>
                </tr>
              </thead>
              <tbody>
                {items.map(item => (
                  <tr key={item.id}>
                    <td><input type="checkbox" checked={selected.has(item.id)} onChange={() => toggle(item.id)} style={{ width: 'auto' }} /></td>
                    <td style={{ fontFamily: 'monospace', fontSize: 11, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.record_id}</td>
                    <td style={{ whiteSpace: 'nowrap', color: '#666' }}>{item.timestamp?.slice(0, 19).replace('T', ' ')}</td>
                    <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.input_preview}</td>
                    <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.output_preview}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {totalPages > 1 && (
              <div className="pagination">
                <button className="btn-secondary btn-sm" onClick={() => loadItems(Number(selectedQueue), page - 1)} disabled={page === 1}>上一页</button>
                <span>{page}/{totalPages}</span>
                <button className="btn-secondary btn-sm" onClick={() => loadItems(Number(selectedQueue), page + 1)} disabled={page === totalPages}>下一页</button>
              </div>
            )}
          </>
        )}
        <div className="flex mt-4">
          <span style={{ fontSize: 12, color: '#999' }}>已选 {selected.size} / 共 {total} 条</span>
          <div style={{ flex: 1 }} />
          <button className="btn-secondary" onClick={onClose}>取消</button>
          <button className="btn-primary" onClick={add} disabled={!selected.size}>添加 {selected.size} 条</button>
        </div>
      </div>
    </div>
  )
}

export default function Datasets() {
  const [datasets, setDatasets] = useState<any[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [items, setItems] = useState<any[]>([])
  const [itemTotal, setItemTotal] = useState(0)
  const [itemPage, setItemPage] = useState(1)
  const [newName, setNewName] = useState('')
  const [showRaw, setShowRaw] = useState(false)
  const [showAnnotated, setShowAnnotated] = useState(false)
  const [sourceFilter, setSourceFilter] = useState('')
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [annFilter, setAnnFilter] = useState('')
  const limit = 50

  const loadDatasets = () => api.listDatasets().then(setDatasets)
  const loadItems = async (did: number, pg = 1) => {
    const data = await api.listDatasetItems(did, pg, limit, sourceFilter, startTime, endTime, annFilter)
    setItems(data.items); setItemTotal(data.total); setItemPage(pg)
  }

  useEffect(() => { loadDatasets() }, [])
  useEffect(() => { if (selected) loadItems(selected) }, [selected, sourceFilter, startTime, endTime, annFilter])

  const create = async () => {
    if (!newName.trim()) return
    await api.createDataset(newName)
    setNewName(''); loadDatasets()
  }

  const del = async (id: number) => {
    if (!confirm('确认删除此数据集？')) return
    await api.deleteDataset(id)
    if (selected === id) setSelected(null)
    loadDatasets()
  }

  const removeItem = async (iid: number) => {
    if (!selected) return
    await api.removeDatasetItem(selected, iid)
    loadItems(selected, itemPage)
    loadDatasets()
  }

  const totalPages = Math.ceil(itemTotal / limit)
  const ds = datasets.find(d => d.id === selected)

  return (
    <div>
      <div className="page-title">数据集</div>
      <div className="card">
        <div className="flex">
          <input type="text" placeholder="新数据集名称..." value={newName} onChange={e => setNewName(e.target.value)} style={{ maxWidth: 280 }} />
          <button className="btn-primary" onClick={create}>创建</button>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: 16 }}>
        <div>
          {datasets.map(d => (
            <div key={d.id} className="card" style={{ cursor: 'pointer', background: selected === d.id ? '#e0e7ff' : '#fff', marginBottom: 8 }} onClick={() => setSelected(d.id)}>
              <div className="flex">
                <div className="flex-1">
                  <strong>{d.name}</strong>
                  <div style={{ fontSize: 12, color: '#666' }}>{d.item_count} 条</div>
                </div>
                <button className="btn-danger btn-sm" onClick={e => { e.stopPropagation(); del(d.id) }}>删除</button>
              </div>
            </div>
          ))}
          {datasets.length === 0 && <div className="empty card">暂无数据集</div>}
        </div>
        <div>
          {selected && ds ? (
            <div className="card">
              <div className="flex" style={{ marginBottom: 12 }}>
                <strong style={{ flex: 1, fontSize: 15 }}>{ds.name}</strong>
                <button className="btn-secondary btn-sm" onClick={() => setShowRaw(true)}>+ 原始数据</button>
                <button className="btn-secondary btn-sm" onClick={() => setShowAnnotated(true)}>+ 标注数据</button>
                <a href={`/api/datasets/${selected}/export`} download style={{ textDecoration: 'none' }}>
                  <button className="btn-primary btn-sm">导出 JSONL</button>
                </a>
              </div>
              <div className="flex" style={{ marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
                <select value={sourceFilter} onChange={e => { setSourceFilter(e.target.value); setItemPage(1) }} style={{ width: 'auto' }}>
                  <option value="">全部来源</option>
                  <option value="raw">原始</option>
                  <option value="annotated">已标注</option>
                </select>
                <label style={{ fontSize: 12, color: '#555', display: 'flex', alignItems: 'center', gap: 4 }}>
                  从 <input type="datetime-local" value={startTime} onChange={e => { setStartTime(e.target.value); setItemPage(1) }} style={{ width: 'auto' }} />
                </label>
                <label style={{ fontSize: 12, color: '#555', display: 'flex', alignItems: 'center', gap: 4 }}>
                  到 <input type="datetime-local" value={endTime} onChange={e => { setEndTime(e.target.value); setItemPage(1) }} style={{ width: 'auto' }} />
                </label>
                <input type="text" placeholder="标注字段搜索..." value={annFilter} onChange={e => { setAnnFilter(e.target.value); setItemPage(1) }} style={{ maxWidth: 180 }} />
              </div>
              <table style={{ fontSize: 12 }}>
                <thead>
                  <tr><th>ID</th><th>时间</th><th>Input</th><th>Output</th><th>来源</th><th>标注</th><th>操作</th></tr>
                </thead>
                <tbody>
                  {items.map(item => (
                    <tr key={item.id}>
                      <td style={{ fontFamily: 'monospace', fontSize: 11, maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.record_id}</td>
                      <td style={{ whiteSpace: 'nowrap', color: '#666' }}>{item.timestamp?.slice(0, 19).replace('T', ' ')}</td>
                      <td style={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.input_preview}</td>
                      <td style={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.output_preview}</td>
                      <td><span className={`badge badge-${item.source}`}>{item.source === 'raw' ? '原始' : '已标注'}</span></td>
                      <td style={{ fontSize: 11, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {item.annotations ? Object.entries(item.annotations).map(([k, v]) => <span key={k} className="tag">{k}: {String(v)}</span>) : '-'}
                      </td>
                      <td><button className="btn-danger btn-sm" onClick={() => removeItem(item.id)}>移除</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {items.length === 0 && <div className="empty">暂无数据，请添加</div>}
              {totalPages > 1 && (
                <div className="pagination">
                  <button className="btn-secondary btn-sm" onClick={() => loadItems(selected, itemPage - 1)} disabled={itemPage === 1}>上一页</button>
                  <span>{itemPage}/{totalPages}</span>
                  <button className="btn-secondary btn-sm" onClick={() => loadItems(selected, itemPage + 1)} disabled={itemPage === totalPages}>下一页</button>
                </div>
              )}
            </div>
          ) : (
            <div className="empty card">请选择一个数据集</div>
          )}
        </div>
      </div>
      {showRaw && selected && (
        <AddRawModal datasetId={selected} onClose={() => setShowRaw(false)} onSaved={() => { setShowRaw(false); loadItems(selected); loadDatasets() }} />
      )}
      {showAnnotated && selected && (
        <AddAnnotatedModal datasetId={selected} onClose={() => setShowAnnotated(false)} onSaved={() => { setShowAnnotated(false); loadItems(selected); loadDatasets() }} />
      )}
    </div>
  )
}
