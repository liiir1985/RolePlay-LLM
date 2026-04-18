const BASE = '/api'

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export const api = {
  // records
  importRecords: (file: File) => {
    const fd = new FormData(); fd.append('file', file)
    return fetch(BASE + '/records/import', { method: 'POST', body: fd }).then(r => r.json())
  },
  listRecords: (page = 1, limit = 50, search = '', startTime = '', endTime = '') => {
    let url = `/records?page=${page}&limit=${limit}&search=${encodeURIComponent(search)}`
    if (startTime) url += `&start_time=${encodeURIComponent(startTime)}`
    if (endTime) url += `&end_time=${encodeURIComponent(endTime)}`
    return req<any>(url)
  },
  getRecord: (id: string) => req<any>(`/records/${encodeURIComponent(id)}`),

  // schemas
  listSchemas: () => req<any[]>('/schemas'),
  createSchema: (body: any) => req<any>('/schemas', { method: 'POST', body: JSON.stringify(body) }),
  getSchema: (id: number) => req<any>(`/schemas/${id}`),
  updateSchema: (id: number, body: any) => req<any>(`/schemas/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteSchema: (id: number) => req<void>(`/schemas/${id}`, { method: 'DELETE' }),

  // queues
  listQueues: () => req<any[]>('/queues'),
  createQueue: (body: any) => req<any>('/queues', { method: 'POST', body: JSON.stringify(body) }),
  getQueue: (id: number) => req<any>(`/queues/${id}`),
  deleteQueue: (id: number) => req<void>(`/queues/${id}`, { method: 'DELETE' }),
  addQueueItems: (qid: number, record_ids: string[]) =>
    req<any>(`/queues/${qid}/items`, { method: 'POST', body: JSON.stringify({ record_ids }) }),
  addAllQueueItems: (qid: number, search = '', startTime = '', endTime = '') =>
    req<any>(`/queues/${qid}/items/all`, { method: 'POST', body: JSON.stringify({ search, start_time: startTime, end_time: endTime }) }),
  listQueueItems: (qid: number, page = 1, limit = 50, status = '', startTime = '', endTime = '') => {
    let url = `/queues/${qid}/items?page=${page}&limit=${limit}`
    if (status) url += `&status=${status}`
    if (startTime) url += `&start_time=${encodeURIComponent(startTime)}`
    if (endTime) url += `&end_time=${encodeURIComponent(endTime)}`
    return req<any>(url)
  },
  getQueueItemIds: (qid: number) => req<number[]>(`/queues/${qid}/item-ids`),
  getQueueItem: (qid: number, iid: number) => req<any>(`/queues/${qid}/items/${iid}`),
  annotateItem: (qid: number, iid: number, values: any) =>
    req<any>(`/queues/${qid}/items/${iid}/annotate`, { method: 'POST', body: JSON.stringify({ values }) }),

  // datasets
  listDatasets: () => req<any[]>('/datasets'),
  createDataset: (name: string) => req<any>('/datasets', { method: 'POST', body: JSON.stringify({ name }) }),
  deleteDataset: (id: number) => req<void>(`/datasets/${id}`, { method: 'DELETE' }),
  addRawItems: (did: number, record_ids: string[]) =>
    req<any>(`/datasets/${did}/items/raw`, { method: 'POST', body: JSON.stringify({ record_ids }) }),
  addAnnotatedItems: (did: number, queue_item_ids: number[]) =>
    req<any>(`/datasets/${did}/items/annotated`, { method: 'POST', body: JSON.stringify({ queue_item_ids }) }),
  listDatasetItems: (did: number, page = 1, limit = 50, source = '', startTime = '', endTime = '', annFilter = '') => {
    let url = `/datasets/${did}/items?page=${page}&limit=${limit}`
    if (source) url += `&source=${source}`
    if (startTime) url += `&start_time=${encodeURIComponent(startTime)}`
    if (endTime) url += `&end_time=${encodeURIComponent(endTime)}`
    if (annFilter) url += `&ann_filter=${encodeURIComponent(annFilter)}`
    return req<any>(url)
  },
  removeDatasetItem: (did: number, iid: number) =>
    req<void>(`/datasets/${did}/items/${iid}`, { method: 'DELETE' }),

  // cleaning (SSE streams)
  mergePreviewStream: (onEvent: (data: any) => void) => {
    return fetch(BASE + '/cleaning/merge-preview', { method: 'POST' }).then(res => {
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      const read = (): Promise<void> => reader.read().then(({ done, value }) => {
        if (done) return
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try { onEvent(JSON.parse(line.slice(6))) } catch {}
          }
        }
        return read()
      })
      return read()
    })
  },
  mergeExecuteStream: (chains: string[][], onEvent: (data: any) => void) => {
    return fetch(BASE + '/cleaning/merge-execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chains }),
    }).then(res => {
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      const read = (): Promise<void> => reader.read().then(({ done, value }) => {
        if (done) return
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try { onEvent(JSON.parse(line.slice(6))) } catch {}
          }
        }
        return read()
      })
      return read()
    })
  },
  fixJsonStringsStream: (onEvent: (data: any) => void) => {
    return fetch(BASE + '/cleaning/fix-json-strings', { method: 'POST' }).then(res => {
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      const read = (): Promise<void> => reader.read().then(({ done, value }) => {
        if (done) return
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try { onEvent(JSON.parse(line.slice(6))) } catch {}
          }
        }
        return read()
      })
      return read()
    })
  },
  mergeConsecutiveSystemStream: (onEvent: (data: any) => void) => {
    return fetch(BASE + '/cleaning/merge-consecutive-system', { method: 'POST' }).then(res => {
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      const read = (): Promise<void> => reader.read().then(({ done, value }) => {
        if (done) return
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try { onEvent(JSON.parse(line.slice(6))) } catch {}
          }
        }
        return read()
      })
      return read()
    })
  },
  dedupSystemMessagesStream: (onEvent: (data: any) => void) => {
    return fetch(BASE + '/cleaning/dedup-system-messages', { method: 'POST' }).then(res => {
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      const read = (): Promise<void> => reader.read().then(({ done, value }) => {
        if (done) return
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try { onEvent(JSON.parse(line.slice(6))) } catch {}
          }
        }
        return read()
      })
      return read()
    })
  },
  removeEmptyRecordsStream: (onEvent: (data: any) => void) => {
    return fetch(BASE + '/cleaning/remove-empty-records', { method: 'POST' }).then(res => {
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      const read = (): Promise<void> => reader.read().then(({ done, value }) => {
        if (done) return
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try { onEvent(JSON.parse(line.slice(6))) } catch {}
          }
        }
        return read()
      })
      return read()
    })
  },
}
