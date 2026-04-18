import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Records from './pages/Records'
import Schemas from './pages/Schemas'
import Queues from './pages/Queues'
import QueueDetail from './pages/QueueDetail'
import QueueItemDetail from './pages/QueueItemDetail'
import Datasets from './pages/Datasets'

export default function App() {
  return (
    <BrowserRouter>
      <div className="layout">
        <nav className="sidebar">
          <h1>Annotation Tool</h1>
          <NavLink to="/records">数据记录</NavLink>
          <NavLink to="/schemas">评估模板</NavLink>
          <NavLink to="/queues">评估队列</NavLink>
          <NavLink to="/datasets">数据集</NavLink>
        </nav>
        <main className="main">
          <Routes>
            <Route path="/" element={<Records />} />
            <Route path="/records" element={<Records />} />
            <Route path="/schemas" element={<Schemas />} />
            <Route path="/queues" element={<Queues />} />
            <Route path="/queues/:queueId" element={<QueueDetail />} />
            <Route path="/queues/:queueId/items/:itemId" element={<QueueItemDetail />} />
            <Route path="/datasets" element={<Datasets />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
