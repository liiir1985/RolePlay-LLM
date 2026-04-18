import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../api'

function AddItemsModal({ queueId, onClose, onSaved }: { queueId: number; onClose: () => void; onSaved: () => void }) {
  const [records, setRecords] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [selectAll, setSelectAll] = useState(false)
  const [adding, setAdding] = useState(false)
  const limit = 20

  const load = async () => {
    const data = await api.listRecords(page, limit, search, startTime, endTime)
    setRecords(data.items)
    setTotal(data.total)
  }
  useEffect(() => { load() }, [page, search, startTime, endTime])

  const toggle = (id: string) => {
    setSelectAll(false)
    setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  }

  const togglePage = () => {
    const pageIds = records.map(r => r.id)
    const allOnPage = pageIds.every(id => selected.has(id))
    setSelected(s => {
      const n = new Set(s)
      pageIds.forEach(id => allOnPage ? n.delete(id) : n.add(id))
      return n
    })
    setSelectAll(false)
  }

  const add = async () => {
    setAdding(true)
    try {
      if (selectAll) {
        const res = await api.addAllQueueItems(queueId, search, startTime, endTime)
        alert(`添加完成：新增 ${res.added} 条`)
      } else {
        await api.addQueueItems(queueId, Array.from(selected))
      }
      onSaved()
    } finally {
      setAdding(false)
    }
  }

  const totalPages = Math.ceil(total / limit)
  const pageAllChecked = records.length > 0 && records.every(r => selected.has(r.id))
  const remainingCount = total - selected.size

  return (
    <div className="modal-overlay">
      <div className="modal" style={{ minWidth: 800, maxWidth: 900 }}>
        <h2>添加数据到队列</h2>
        <div className="flex" style={{ marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
          <input type="text" placeholder="搜索 ID..." value={search} onChange={e => { setSearch(e.target.value); setPage(1); setSelectAll(false) }} style={{ maxWidth: 200 }} />
          <label style={{ fontSize: 12, color: '#555', display: 'flex', alignItems: 'center', gap: 4 }}>
            从 <input type="datetime-local" value={startTime} onChange={e => { setStartTime(e.target.value); setPage(1); setSelectAll(false) }} style={{ width: 'auto' }} />
          </label>
          <label style={{ fontSize: 12, color: '#555', display: 'flex', alignItems: 'center', gap: 4 }}>
            到 <input type="datetime-local" value={endTime} onChange={e => { setEndTime(e.target.value); setPage(1); setSelectAll(false) }} style={{ width: 'auto' }} />
          </label>
          <span style={{ fontSize: 12, color: '#999', marginLeft: 'auto' }}>
            {selectAll ? `全部 ${total} 条` : `已选 ${selected.size} 条`} / 共 {total} 条
          </span>
        </div>
        {selectAll && (
          <div style={{ background: '#e0e7ff', padding: '6px 12px', borderRadius: 4, marginBottom: 8, fontSize: 13 }}>
            将添加当前筛选条件下的全部 {total} 条数据
            <button className="btn-secondary btn-sm" style={{ marginLeft: 8 }} onClick={() => setSelectAll(false)}>取消全选</button>
          </div>
        )}
        <table style={{ fontSize: 12 }}>
          <thead>
            <tr>
              <th style={{ width: 30 }}><input type="checkbox" checked={pageAllChecked && !selectAll} onChange={togglePage} style={{ width: 'auto' }} /></th>
              <th>ID</th><th>时间</th><th>Input (前100字)</th><th>Output (前100字)</th>
            </tr>
          </thead>
          <tbody>
            {records.map(r => (
              <tr key={r.id}>
                <td><input type="checkbox" checked={selectAll || selected.has(r.id)} onChange={() => toggle(r.id)} style={{ width: 'auto' }} /></td>
                <td style={{ fontFamily: 'monospace', fontSize: 11, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.id}</td>
                <td style={{ whiteSpace: 'nowrap', color: '#666' }}>{r.timestamp?.slice(0, 19).replace('T', ' ')}</td>
                <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.input_preview}</td>
                <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.output_preview}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!selectAll && selected.size > 0 && remainingCount > 0 && (
          <div style={{ textAlign: 'center', padding: '8px 0', fontSize: 13 }}>
            已选当前页 {selected.size} 条，
            <button className="btn-secondary btn-sm" onClick={() => setSelectAll(true)}>
              选择全部 {total} 条（含其他页）
            </button>
          </div>
        )}
        {totalPages > 1 && (
          <div className="pagination">
            <button className="btn-secondary btn-sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>上一页</button>
            <span>{page}/{totalPages}</span>
            <button className="btn-secondary btn-sm" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}>下一页</button>
          </div>
        )}
        <div className="flex mt-4">
          <button className="btn-secondary" onClick={onClose}>取消</button>
          <button className="btn-primary" onClick={add} disabled={adding || (!selectAll && selected.size === 0)}>
            {adding ? '添加中...' : selectAll ? `添加全部 ${total} 条` : `添加 ${selected.size} 条`}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function QueueDetail() {
  const { queueId } = useParams<{ queueId: string }>()
  const qid = Number(queueId)
  const navigate = useNavigate()
  const [queue, setQueue] = useState<any>(null)
  const [items, setItems] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState('')
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const limit = 20

  const loadQueue = () => api.getQueue(qid).then(setQueue)
  const loadItems = async () => {
    const data = await api.listQueueItems(qid, page, limit, statusFilter, startTime, endTime)
    setItems(data.items)
    setTotal(data.total)
  }

  useEffect(() => { loadQueue() }, [qid])
  useEffect(() => { loadItems() }, [qid, page, statusFilter, startTime, endTime])

  const totalPages = Math.ceil(total / limit)

  if (!queue) return <div>加载中...</div>

  return (
    <div>
      <div className="flex" style={{ marginBottom: 20 }}>
        <button className="btn-secondary btn-sm" onClick={() => navigate('/queues')}>← 返回</button>
        <div className="page-title" style={{ margin: '0 0 0 12px', flex: 1 }}>{queue.name}</div>
        <button className="btn-primary" onClick={() => setShowAdd(true)}>+ 添加数据</button>
      </div>
      <div className="card" style={{ marginBottom: 12, padding: '10px 16px', fontSize: 13, color: '#555' }}>
        模板：<strong>{queue.schema_name}</strong> &nbsp;|&nbsp; 共 {total} 条
      </div>
      <div className="card">
        <div className="flex" style={{ marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
          <select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1) }} style={{ width: 'auto' }}>
            <option value="">全部</option>
            <option value="pending">待标注</option>
            <option value="annotated">已标注</option>
          </select>
          <label style={{ fontSize: 12, color: '#555', display: 'flex', alignItems: 'center', gap: 4 }}>
            从 <input type="datetime-local" value={startTime} onChange={e => { setStartTime(e.target.value); setPage(1) }} style={{ width: 'auto' }} />
          </label>
          <label style={{ fontSize: 12, color: '#555', display: 'flex', alignItems: 'center', gap: 4 }}>
            到 <input type="datetime-local" value={endTime} onChange={e => { setEndTime(e.target.value); setPage(1) }} style={{ width: 'auto' }} />
          </label>
          {(startTime || endTime) && <button className="btn-secondary btn-sm" onClick={() => { setStartTime(''); setEndTime(''); setPage(1) }}>清除时间</button>}
        </div>
        <table>
          <thead>
            <tr><th>ID</th><th>时间</th><th>Input (前100字)</th><th>Output (前100字)</th><th>状态</th><th>操作</th></tr>
          </thead>
          <tbody>
            {items.map(item => (
              <tr key={item.id}>
                <td style={{ fontFamily: 'monospace', fontSize: 11, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.record_id}</td>
                <td style={{ fontSize: 12, color: '#666', whiteSpace: 'nowrap' }}>{item.timestamp?.slice(0, 19).replace('T', ' ')}</td>
                <td style={{ fontSize: 12, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.input_preview}</td>
                <td style={{ fontSize: 12, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.output_preview}</td>
                <td><span className={`badge badge-${item.status}`}>{item.status === 'annotated' ? '已标注' : '待标注'}</span></td>
                <td>
                  <button className="btn-secondary btn-sm" onClick={() => navigate(`/queues/${qid}/items/${item.id}`)}>
                    {item.status === 'annotated' ? '查看/编辑' : '标注'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {items.length === 0 && <div className="empty">暂无数据</div>}
        {totalPages > 1 && (
          <div className="pagination">
            <button className="btn-secondary btn-sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>上一页</button>
            <span>{page}/{totalPages}</span>
            <button className="btn-secondary btn-sm" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}>下一页</button>
          </div>
        )}
      </div>
      {showAdd && (
        <AddItemsModal queueId={qid} onClose={() => setShowAdd(false)} onSaved={() => { setShowAdd(false); loadItems() }} />
      )}
    </div>
  )
}
