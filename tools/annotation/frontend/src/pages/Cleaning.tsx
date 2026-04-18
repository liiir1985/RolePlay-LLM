import { useState } from 'react'
import { api } from '../api'

interface ChainRecord {
  id: string
  timestamp: string
  msg_count: number
}

interface Chain {
  index: number
  records: ChainRecord[]
  surviving_id: string
  delete_count: number
}

interface PreviewResult {
  chains: Chain[]
  total_chains: number
  total_mergeable: number
}

interface ProgressState {
  active: boolean
  stage: string
  message: string
  progress: number
  total: number
}

export default function Cleaning() {
  const [progress, setProgress] = useState<ProgressState>({ active: false, stage: '', message: '', progress: 0, total: 0 })
  const [preview, setPreview] = useState<PreviewResult | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [result, setResult] = useState<{ merged: number; deleted: number } | null>(null)
  const [error, setError] = useState('')

  const scan = async () => {
    setError('')
    setResult(null)
    setPreview(null)
    setSelected(new Set())
    setProgress({ active: true, stage: 'loading', message: '正在加载记录...', progress: 0, total: 0 })
    try {
      await api.mergePreviewStream((event) => {
        if (event.stage === 'done') {
          setPreview(event.result)
          setProgress(p => ({ ...p, active: false }))
        } else if (event.stage === 'error') {
          setError(event.message)
          setProgress(p => ({ ...p, active: false }))
        } else {
          setProgress({ active: true, stage: event.stage, message: event.message, progress: event.progress || 0, total: event.total || 0 })
        }
      })
    } catch (e: any) {
      setError(e.message || '扫描失败')
      setProgress(p => ({ ...p, active: false }))
    }
  }

  const toggleAll = () => {
    if (!preview) return
    if (selected.size === preview.chains.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(preview.chains.map(c => c.index)))
    }
  }

  const toggle = (idx: number) => {
    setSelected(s => {
      const n = new Set(s)
      n.has(idx) ? n.delete(idx) : n.add(idx)
      return n
    })
  }

  const execute = async () => {
    if (!selected.size) return
    if (!confirm(`确认合并 ${selected.size} 条会话链？此操作不可撤销。`)) return
    setError('')
    setProgress({ active: true, stage: 'merging', message: '正在执行合并...', progress: 0, total: selected.size })
    try {
      const chains = preview!.chains
        .filter(c => selected.has(c.index))
        .map(c => c.records.map(r => r.id))
      await api.mergeExecuteStream(chains, (event) => {
        if (event.stage === 'done') {
          setResult(event.result)
          setPreview(null)
          setSelected(new Set())
          setProgress(p => ({ ...p, active: false }))
        } else if (event.stage === 'error') {
          setError(event.message)
          setProgress(p => ({ ...p, active: false }))
        } else {
          setProgress({ active: true, stage: event.stage, message: event.message, progress: event.progress || 0, total: event.total || 0 })
        }
      })
    } catch (e: any) {
      setError(e.message || '执行失败')
      setProgress(p => ({ ...p, active: false }))
    }
  }

  const pct = progress.total > 0 ? Math.round((progress.progress / progress.total) * 100) : 0

  return (
    <div>
      <h2 className="page-title">数据清洗</h2>

      <div className="card">
        <div className="flex" style={{ marginBottom: 16 }}>
          <h3 style={{ fontSize: 15, fontWeight: 600 }}>合并会话记录</h3>
          <button className="btn-primary" onClick={scan} disabled={progress.active} style={{ marginLeft: 'auto' }}>
            扫描
          </button>
        </div>
        <p style={{ fontSize: 12, color: '#666', marginBottom: 12 }}>
          检测同一会话的多条记录并合并为一条完整记录，保留最早记录的 ID，删除重复条目。
        </p>

        {error && <div style={{ color: '#f38ba8', marginBottom: 12 }}>{error}</div>}

        {result && (
          <div style={{ background: '#d1fae5', color: '#065f46', padding: 12, borderRadius: 6, marginBottom: 12 }}>
            合并完成：合并了 {result.merged} 条会话链，删除了 {result.deleted} 条重复记录。
          </div>
        )}

        {preview && (
          <>
            <div className="flex" style={{ marginBottom: 8 }}>
              <span style={{ fontSize: 12, color: '#666' }}>
                检测到 {preview.total_chains} 条可合并会话链，涉及 {preview.total_mergeable} 条记录
              </span>
              {preview.chains.length > 0 && (
                <button className="btn-secondary btn-sm" onClick={toggleAll} style={{ marginLeft: 'auto' }}>
                  {selected.size === preview.chains.length ? '取消全选' : '全选'}
                </button>
              )}
            </div>

            {preview.chains.length === 0 ? (
              <div className="empty">未检测到可合并的会话记录</div>
            ) : (
              <>
                <div style={{ maxHeight: 400, overflowY: 'auto', border: '1px solid #eee', borderRadius: 4 }}>
                  <table style={{ fontSize: 12 }}>
                    <thead>
                      <tr>
                        <th style={{ width: 30 }}>
                          <input type="checkbox" checked={selected.size === preview.chains.length} onChange={toggleAll} style={{ width: 'auto' }} />
                        </th>
                        <th>存活 ID</th>
                        <th>记录数</th>
                        <th>时间范围</th>
                        <th>轮次变化</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.chains.map(chain => (
                        <tr key={chain.index}>
                          <td>
                            <input type="checkbox" checked={selected.has(chain.index)} onChange={() => toggle(chain.index)} style={{ width: 'auto' }} />
                          </td>
                          <td style={{ fontFamily: 'monospace', fontSize: 11, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {chain.surviving_id}
                          </td>
                          <td>{chain.records.length} 条</td>
                          <td style={{ whiteSpace: 'nowrap', color: '#666' }}>
                            {chain.records[0]?.timestamp?.slice(0, 19).replace('T', ' ')} ~ {chain.records[chain.records.length - 1]?.timestamp?.slice(11, 19)}
                          </td>
                          <td style={{ color: '#666' }}>
                            {chain.records.map(r => r.msg_count).join(' → ')}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="flex mt-4">
                  <button className="btn-primary" onClick={execute} disabled={!selected.size}>
                    执行合并 ({selected.size} 条链)
                  </button>
                </div>
              </>
            )}
          </>
        )}
      </div>

      {progress.active && (
        <div className="modal-overlay">
          <div className="modal" style={{ minWidth: 400, maxWidth: 480, textAlign: 'center' }}>
            <h2 style={{ marginBottom: 16 }}>{progress.stage === 'merging' ? '正在合并' : '正在扫描'}</h2>
            <p style={{ fontSize: 13, color: '#555', marginBottom: 16 }}>{progress.message}</p>
            <div style={{ background: '#e5e7eb', borderRadius: 4, height: 20, overflow: 'hidden', marginBottom: 8 }}>
              <div style={{
                background: '#89b4fa',
                height: '100%',
                width: `${pct}%`,
                transition: 'width 0.3s ease',
                borderRadius: 4,
              }} />
            </div>
            <span style={{ fontSize: 12, color: '#888' }}>{pct}%</span>
          </div>
        </div>
      )}
    </div>
  )
}
