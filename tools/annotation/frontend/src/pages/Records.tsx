import { useState, useEffect, useRef } from 'react'
import { api } from '../api'

export default function Records() {
  const [records, setRecords] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [importing, setImporting] = useState(false)
  const [msg, setMsg] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const limit = 50

  const load = async () => {
    const data = await api.listRecords(page, limit, search, startTime, endTime)
    setRecords(data.items)
    setTotal(data.total)
  }

  useEffect(() => { load() }, [page, search, startTime, endTime])

  const handleImport = async () => {
    const file = fileRef.current?.files?.[0]
    if (!file) return
    setImporting(true)
    try {
      const res = await api.importRecords(file)
      setMsg(`导入完成：新增 ${res.inserted} 条，跳过 ${res.skipped} 条`)
      load()
    } catch (e: any) {
      setMsg('导入失败：' + e.message)
    } finally {
      setImporting(false)
    }
  }

  const totalPages = Math.ceil(total / limit)

  return (
    <div>
      <div className="page-title">数据记录</div>
      <div className="card">
        <div className="flex">
          <input type="file" accept=".jsonl" ref={fileRef} style={{ flex: 1 }} />
          <button className="btn-primary" onClick={handleImport} disabled={importing}>
            {importing ? '导入中...' : '导入 JSONL'}
          </button>
        </div>
        {msg && <div className="mt-2" style={{ color: '#555' }}>{msg}</div>}
      </div>
      <div className="card">
        <div className="flex" style={{ marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
          <input
            type="text" placeholder="搜索 ID..." value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
            style={{ maxWidth: 240 }}
          />
          <label style={{ fontSize: 12, color: '#555', display: 'flex', alignItems: 'center', gap: 4 }}>
            从 <input type="datetime-local" value={startTime} onChange={e => { setStartTime(e.target.value); setPage(1) }} style={{ width: 'auto' }} />
          </label>
          <label style={{ fontSize: 12, color: '#555', display: 'flex', alignItems: 'center', gap: 4 }}>
            到 <input type="datetime-local" value={endTime} onChange={e => { setEndTime(e.target.value); setPage(1) }} style={{ width: 'auto' }} />
          </label>
          {(startTime || endTime) && <button className="btn-secondary btn-sm" onClick={() => { setStartTime(''); setEndTime(''); setPage(1) }}>清除时间</button>}
          <span style={{ color: '#999', fontSize: 12, marginLeft: 'auto' }}>共 {total} 条</span>
        </div>
        <table>
          <thead>
            <tr><th style={{ width: '25%' }}>ID</th><th style={{ width: '15%' }}>时间</th><th style={{ width: '30%' }}>Input (前100字)</th><th style={{ width: '30%' }}>Output (前100字)</th></tr>
          </thead>
          <tbody>
            {records.map(r => (
              <tr key={r.id}>
                <td style={{ fontFamily: 'monospace', fontSize: 11, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.id}</td>
                <td style={{ fontSize: 12, color: '#666', whiteSpace: 'nowrap' }}>{r.timestamp?.slice(0, 19).replace('T', ' ')}</td>
                <td style={{ fontSize: 12, maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.input_preview}</td>
                <td style={{ fontSize: 12, maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.output_preview}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {records.length === 0 && <div className="empty">暂无数据，请先导入 JSONL 文件</div>}
        {totalPages > 1 && (
          <div className="pagination">
            <button className="btn-secondary btn-sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>上一页</button>
            <span>{page} / {totalPages}</span>
            <button className="btn-secondary btn-sm" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}>下一页</button>
          </div>
        )}
      </div>
    </div>
  )
}
