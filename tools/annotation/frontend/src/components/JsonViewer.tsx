import { JsonView, darkStyles } from 'react-json-view-lite'
import 'react-json-view-lite/dist/index.css'

const customStyles = {
  ...darkStyles,
  container: 'json-viewer-container',
}

function parseRecursive(val: unknown): unknown {
  if (typeof val === 'string') {
    try {
      const parsed = JSON.parse(val)
      if (typeof parsed === 'object' && parsed !== null) {
        return parseRecursive(parsed)
      }
    } catch { /* not JSON, keep as string */ }
    return val
  }
  if (Array.isArray(val)) return val.map(parseRecursive)
  if (typeof val === 'object' && val !== null) {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(val)) {
      out[k] = parseRecursive(v)
    }
    return out
  }
  return val
}

function StringRenderer({ value }: { value: string }) {
  if (!value.includes('\n')) return <span>"{value}"</span>
  return (
    <span style={{ whiteSpace: 'pre-wrap', display: 'inline-block', verticalAlign: 'top' }}>
      "{value}"
    </span>
  )
}

export default function JsonViewer({ data, initialExpanded = 2 }: { data: unknown; initialExpanded?: number }) {
  const parsed = parseRecursive(data)

  let depth = 0
  const shouldExpand = (_level: number) => {
    depth++
    return _level < initialExpanded
  }

  return (
    <div className="json-viewer-wrapper">
      <JsonView
        data={parsed as object}
        shouldExpandNode={shouldExpand}
        style={customStyles}
        clickToExpandNode
      />
    </div>
  )
}
