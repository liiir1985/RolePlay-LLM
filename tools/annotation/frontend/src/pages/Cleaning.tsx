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
  const [fixResult, setFixResult] = useState<{ fixed: number; total: number } | null>(null)
  const [removeResult, setRemoveResult] = useState<{ deleted: number; total: number } | null>(null)
  const [dedupResult, setDedupResult] = useState<{ modified: number; messages_removed: number; total: number } | null>(null)
  const [mergeConsResult, setMergeConsResult] = useState<{ modified: number; messages_merged: number; total: number } | null>(null)
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

  const fixJsonStrings = async () => {
    if (!confirm('将扫描所有记录，把 input/output 中字符串形式的 JSON 字段替换为 JSON 对象。确认执行？')) return
    setError('')
    setFixResult(null)
    setProgress({ active: true, stage: 'processing', message: '正在处理...', progress: 0, total: 0 })
    try {
      await api.fixJsonStringsStream((event) => {
        if (event.stage === 'done') {
          setFixResult(event.result)
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

  const removeEmptyRecords = async () => {
    if (!confirm('将删除所有没有 assistant 有效发言且 output 为空的记录。确认执行？')) return
    setError('')
    setRemoveResult(null)
    setProgress({ active: true, stage: 'processing', message: '正在扫描...', progress: 0, total: 0 })
    try {
      await api.removeEmptyRecordsStream((event) => {
        if (event.stage === 'done') {
          setRemoveResult(event.result)
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

  const dedupSystemMessages = async () => {
    if (!confirm('将扫描所有记录，去除 system message 中与更早 system message 重复的子串。确认执行？')) return
    setError('')
    setDedupResult(null)
    setProgress({ active: true, stage: 'processing', message: '正在扫描...', progress: 0, total: 0 })
    try {
      await api.dedupSystemMessagesStream((event) => {
        if (event.stage === 'done') {
          setDedupResult(event.result)
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

  const mergeConsecutiveSystem = async () => {
    if (!confirm('将扫描所有记录，合并连续的 system messages 为一条。确认执行？')) return
    setError('')
    setMergeConsResult(null)
    setProgress({ active: true, stage: 'processing', message: '正在扫描...', progress: 0, total: 0 })
    try {
      await api.mergeConsecutiveSystemStream((event) => {
        if (event.stage === 'done') {
          setMergeConsResult(event.result)
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

      <div className="card">
        <div className="flex" style={{ marginBottom: 16 }}>
          <h3 style={{ fontSize: 15, fontWeight: 600 }}>修复 JSON 字符串字段</h3>
          <button className="btn-primary" onClick={fixJsonStrings} disabled={progress.active} style={{ marginLeft: 'auto' }}>
            执行
          </button>
        </div>
        <p style={{ fontSize: 12, color: '#666', marginBottom: 12 }}>
          扫描所有记录的 input/output，将其中字符串形式的 JSON 字段（如 <code>{'{"key":"val"}'}</code>）替换为真正的 JSON 对象。
        </p>
        {fixResult && (
          <div style={{ background: '#d1fae5', color: '#065f46', padding: 12, borderRadius: 6 }}>
            完成：共处理 {fixResult.total} 条记录，修复了 {fixResult.fixed} 条。
          </div>
        )}
      </div>

      <div className="card">
        <div className="flex" style={{ marginBottom: 16 }}>
          <h3 style={{ fontSize: 15, fontWeight: 600 }}>删除空记录</h3>
          <button className="btn-primary" onClick={removeEmptyRecords} disabled={progress.active} style={{ marginLeft: 'auto' }}>
            执行
          </button>
        </div>
        <p style={{ fontSize: 12, color: '#666', marginBottom: 12 }}>
          删除 input 中没有 assistant 有效发言且 output 为空（content/tool_calls/function_call 均为空）的记录。
        </p>
        {removeResult && (
          <div style={{ background: '#d1fae5', color: '#065f46', padding: 12, borderRadius: 6 }}>
            完成：共扫描 {removeResult.total} 条记录，删除了 {removeResult.deleted} 条。
          </div>
        )}
      </div>

      <div className="card">
        <div className="flex" style={{ marginBottom: 16 }}>
          <h3 style={{ fontSize: 15, fontWeight: 600 }}>合并连续 System Message</h3>
          <button className="btn-primary" onClick={mergeConsecutiveSystem} disabled={progress.active} style={{ marginLeft: 'auto' }}>
            执行
          </button>
        </div>
        <p style={{ fontSize: 12, color: '#666', marginBottom: 12 }}>
          将同一条记录中连续的多个 system message 合并为一条，内容以换行拼接。
        </p>
        {mergeConsResult && (
          <div style={{ background: '#d1fae5', color: '#065f46', padding: 12, borderRadius: 6 }}>
            完成：共扫描 {mergeConsResult.total} 条记录，修改了 {mergeConsResult.modified} 条，合并了 {mergeConsResult.messages_merged} 条 message。
          </div>
        )}
      </div>

      <div className="card">
        <div className="flex" style={{ marginBottom: 16 }}>
          <h3 style={{ fontSize: 15, fontWeight: 600 }}>去除重复 System Message</h3>
          <button className="btn-primary" onClick={dedupSystemMessages} disabled={progress.active} style={{ marginLeft: 'auto' }}>
            执行
          </button>
        </div>
        <p style={{ fontSize: 12, color: '#666', marginBottom: 12 }}>
          从后往前比对 system messages，删除与更早 system message 中超过10字的重复子串。如果删除后内容为空则移除该条 message。
        </p>
        {dedupResult && (
          <div style={{ background: '#d1fae5', color: '#065f46', padding: 12, borderRadius: 6 }}>
            完成：共扫描 {dedupResult.total} 条记录，修改了 {dedupResult.modified} 条，移除了 {dedupResult.messages_removed} 条空 message。
          </div>
        )}
      </div>

      {progress.active && (
        <div className="modal-overlay">
          <div className="modal" style={{ minWidth: 400, maxWidth: 480, textAlign: 'center' }}>
            <h2 style={{ marginBottom: 16 }}>
              {progress.stage === 'merging' ? '正在合并' : progress.stage === 'deleting' ? '正在删除' : progress.stage === 'updating' ? '正在更新' : progress.stage === 'processing' ? '正在处理' : '正在扫描'}
            </h2>
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
