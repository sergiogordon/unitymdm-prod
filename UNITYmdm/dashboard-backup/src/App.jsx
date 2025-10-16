import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { ThemeProvider } from './contexts/ThemeContext'
import DeviceList from './pages/DeviceList'
import DeviceDetail from './pages/DeviceDetail'
import './index.css'

function App() {
  return (
    <ThemeProvider>
      <Router>
        <Routes>
          <Route path="/" element={<DeviceList />} />
          <Route path="/d/:deviceId" element={<DeviceDetail />} />
        </Routes>
      </Router>
    </ThemeProvider>
  )
}

export default App
