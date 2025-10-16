import { useState, useEffect, useRef } from 'react'
import { Settings, Moon, Sun } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { useTheme } from '../contexts/ThemeContext'
import StatCard from '../components/StatCard'
import SegmentedControl from '../components/SegmentedControl'
import DeviceDrawer from '../components/DeviceDrawer'
import LoadingSkeleton from '../components/LoadingSkeleton'
import RefreshIndicator from '../components/RefreshIndicator'
import SettingsModal from '../components/SettingsModal'
import ErrorState from '../components/ErrorState'
import AlertsPill from '../components/AlertsPill'
import Toast from '../components/Toast'

function DeviceList() {
  const [devices, setDevices] = useState([])
  const [filter, setFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [stats, setStats] = useState({ total: 0, online: 0, offline: 0, alerts: 0 })
  const [selectedDevice, setSelectedDevice] = useState(null)
  const [lastUpdate, setLastUpdate] = useState(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [showAlertBadges, setShowAlertBadges] = useState(() => {
    return localStorage.getItem('showAlertBadges') !== 'false'
  })
  const [compactView, setCompactView] = useState(() => {
    return localStorage.getItem('compactView') === 'true'
  })
  const [toast, setToast] = useState(null)
  const { isDark, toggleTheme } = useTheme()
  const intervalRef = useRef(null)

  useEffect(() => {
    const storedInterval = localStorage.getItem('refreshInterval') || '10'
    const intervalMs = parseInt(storedInterval) * 1000

    fetchDevices()
    intervalRef.current = setInterval(fetchDevices, intervalMs)

    const handleSettingsChange = (e) => {
      const newInterval = parseInt(e.detail.refreshInterval) * 1000
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
      intervalRef.current = setInterval(fetchDevices, newInterval)
      
      setShowAlertBadges(localStorage.getItem('showAlertBadges') !== 'false')
      setCompactView(localStorage.getItem('compactView') === 'true')
    }

    window.addEventListener('settingsChanged', handleSettingsChange)
    
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
      window.removeEventListener('settingsChanged', handleSettingsChange)
    }
  }, [])

  async function fetchDevices() {
    try {
      setError(false)
      const response = await fetch('/v1/devices')
      if (!response.ok) throw new Error('Failed to fetch')
      const data = await response.json()
      setDevices(data)
      
      const online = data.filter(d => d.status === 'online').length
      const offline = data.filter(d => d.status === 'offline').length
      const alerts = data.filter(d => {
        if (!d.last_status) return false
        const battery = d.last_status.battery?.pct || 100
        const unityInstalled = d.last_status.app_versions?.unity?.installed || false
        const unityRunning = d.last_status.unity_running_signals?.has_service_notification || false
        return d.status === 'offline' || battery < 20 || !unityInstalled || !unityRunning
      }).length
      
      setStats({ total: data.length, online, offline, alerts })
      setLoading(false)
      setLastUpdate(Date.now())
    } catch (err) {
      console.error('Failed to fetch devices:', err)
      setError(true)
      setLoading(false)
    }
  }

  function getStatusInfo(device) {
    if (device.status === 'offline') {
      return { color: 'bg-rose-500', text: 'Offline' }
    }
    
    if (!device.last_status) return { color: 'bg-neutral-400', text: 'Unknown' }
    
    const battery = device.last_status.battery?.pct || 100
    const unityInstalled = device.last_status.app_versions?.unity?.installed || false
    const unityRunning = device.last_status.unity_running_signals?.has_service_notification || false
    
    if (battery < 20 || !unityInstalled || !unityRunning) {
      return { color: 'bg-amber-500', text: 'Alert' }
    }
    
    return { color: 'bg-emerald-500', text: 'Online' }
  }

  function filterDevices(devices) {
    if (filter === 'all') return devices
    
    return devices.filter(device => {
      if (!device.last_status) return filter === 'offline'
      
      const battery = device.last_status.battery?.pct || 100
      const unityInstalled = device.last_status.app_versions?.unity?.installed || false
      const unityRunning = device.last_status.unity_running_signals?.has_service_notification || false
      
      if (filter === 'offline') return device.status === 'offline'
      if (filter === 'unity_down') return !unityRunning
      if (filter === 'low_battery') return battery < 20
      if (filter === 'wrong_version') return !unityInstalled
      
      return true
    })
  }

  const filtered = filterDevices(devices)

  const filterOptions = [
    { value: 'all', label: 'All' },
    { value: 'offline', label: 'Offline' },
    { value: 'unity_down', label: 'Unity Down' },
    { value: 'low_battery', label: 'Low Battery' },
    { value: 'wrong_version', label: 'Wrong Version' },
  ]

  return (
    <div className={`min-h-screen bg-neutral-50 dark:bg-black transition-colors ${compactView ? 'text-sm' : ''} font-sans`}>
      <header className="sticky top-0 z-30 bg-white/80 dark:bg-neutral-900/80 backdrop-blur-xl border-b border-neutral-200/50 dark:border-neutral-800/50">
        <div className="max-w-[1280px] mx-auto px-6 sm:px-8 py-4 flex items-center justify-between">
          <h1 className="text-xl font-semibold tracking-tight text-neutral-900 dark:text-white">
            Unity Micro-MDM
          </h1>
          <div className="flex items-center gap-3">
            <RefreshIndicator lastUpdate={lastUpdate} />
            <AlertsPill count={stats.alerts} />
            <button
              onClick={toggleTheme}
              className="p-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-lg transition-colors"
              aria-label="Toggle theme"
            >
              {isDark ? (
                <Sun className="h-5 w-5 text-neutral-600 dark:text-neutral-400" />
              ) : (
                <Moon className="h-5 w-5 text-neutral-600 dark:text-neutral-400" />
              )}
            </button>
            <button
              onClick={() => setSettingsOpen(true)}
              className="p-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-lg transition-colors"
              aria-label="Settings"
            >
              <Settings className="h-5 w-5 text-neutral-600 dark:text-neutral-400" />
            </button>
          </div>
        </div>
      </header>

      <main className={`max-w-[1280px] mx-auto px-6 sm:px-8 ${compactView ? 'py-4' : 'py-6'}`}>
        <div className={`grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 ${compactView ? 'gap-3 mb-4' : 'gap-4 mb-6'}`}>
          <StatCard label="Total Devices" value={stats.total} compact={compactView} />
          <StatCard label="Online" value={stats.online} compact={compactView} />
          <StatCard label="Offline" value={stats.offline} semanticColor="red" compact={compactView} />
          <StatCard label="Active Alerts" value={stats.alerts} semanticColor="amber" compact={compactView} />
        </div>

        <div className="sticky top-[73px] z-20 -mx-6 sm:-mx-8 px-6 sm:px-8 py-4 bg-neutral-50/95 dark:bg-black/95 backdrop-blur-md border-b border-neutral-200/50 dark:border-neutral-800/50 mb-6">
          <div className="flex items-center justify-center">
            <SegmentedControl
              options={filterOptions}
              value={filter}
              onChange={setFilter}
            />
          </div>
        </div>

        {loading ? (
          <LoadingSkeleton />
        ) : error ? (
          <ErrorState onRetry={fetchDevices} />
        ) : (
          <div className="bg-white dark:bg-neutral-900 rounded-2xl shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead className="sticky top-[137px] bg-white/95 dark:bg-neutral-900/95 backdrop-blur-md border-b border-neutral-200 dark:border-neutral-800">
                  <tr>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-semibold text-neutral-600 dark:text-neutral-400 uppercase tracking-wider">
                      Status
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-semibold text-neutral-600 dark:text-neutral-400 uppercase tracking-wider">
                      Alias
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-semibold text-neutral-600 dark:text-neutral-400 uppercase tracking-wider">
                      <span className="hidden sm:inline">Last Seen</span>
                      <span className="sm:hidden">Seen</span>
                    </th>
                    <th scope="col" className="px-6 py-3 text-right text-xs font-semibold text-neutral-600 dark:text-neutral-400 uppercase tracking-wider">
                      <span className="hidden sm:inline">Battery</span>
                      <span className="sm:hidden">Bat</span>
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-semibold text-neutral-600 dark:text-neutral-400 uppercase tracking-wider">
                      <span className="hidden sm:inline">Network</span>
                      <span className="sm:hidden">Net</span>
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-semibold text-neutral-600 dark:text-neutral-400 uppercase tracking-wider">
                      Unity
                    </th>
                    <th scope="col" className="px-6 py-3 text-right text-xs font-semibold text-neutral-600 dark:text-neutral-400 uppercase tracking-wider hidden min-[480px]:table-cell">
                      RAM
                    </th>
                    <th scope="col" className="px-6 py-3 text-right text-xs font-semibold text-neutral-600 dark:text-neutral-400 uppercase tracking-wider">
                      Uptime
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                  {filtered.map((device) => {
                    const statusInfo = getStatusInfo(device)
                    return (
                      <tr
                        key={device.id}
                        onClick={() => setSelectedDevice(device)}
                        className="hover:bg-neutral-50 dark:hover:bg-neutral-800/50 cursor-pointer transition-colors"
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => e.key === 'Enter' && setSelectedDevice(device)}
                      >
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="flex items-center gap-2">
                            <div className={`w-2 h-2 rounded-full ${statusInfo.color} transition-colors duration-300`} />
                            <span className="text-sm text-neutral-900 dark:text-neutral-200">
                              {statusInfo.text}
                            </span>
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span className="text-sm font-medium text-accent hover:underline">
                            {device.alias}
                          </span>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          {device.last_seen ? (
                            <div className="flex flex-col">
                              <span className="text-sm text-neutral-900 dark:text-neutral-200">
                                {formatDistanceToNow(new Date(device.last_seen), { addSuffix: true }).replace(' ago', '')}
                              </span>
                              <span className="text-xs text-neutral-400 dark:text-neutral-600">
                                ({new Date(device.last_seen).toISOString()})
                              </span>
                            </div>
                          ) : (
                            <span className="text-sm text-neutral-600 dark:text-neutral-400">Never</span>
                          )}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-neutral-900 dark:text-neutral-200">
                          {device.last_status?.battery?.pct ?? '-'}%
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-neutral-900 dark:text-neutral-200">
                          {device.last_status?.network?.transport === 'wifi' 
                            ? device.last_status?.network?.wifi_ssid || 'WiFi'
                            : device.last_status?.network?.carrier_name || device.last_status?.network?.transport || '-'}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          {device.last_status?.app_versions?.unity?.installed ? (
                            <div className="flex items-center gap-2">
                              <span className="text-sm text-neutral-900 dark:text-neutral-200">
                                v{device.last_status.app_versions.unity.version_name}
                              </span>
                              {showAlertBadges && (
                                device.last_status.unity_running_signals?.has_service_notification ? (
                                  <span className="px-2 py-0.5 bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 text-xs rounded-full">
                                    running
                                  </span>
                                ) : (
                                  <span className="px-2 py-0.5 bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 text-xs rounded-full">
                                    down
                                  </span>
                                )
                              )}
                            </div>
                          ) : (
                            <span className="text-sm text-rose-600 dark:text-rose-400">Not installed</span>
                          )}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-neutral-900 dark:text-neutral-200 hidden min-[480px]:table-cell">
                          {device.last_status?.memory?.pressure_pct ?? '-'}%
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-neutral-900 dark:text-neutral-200">
                          {device.last_status?.system?.uptime_seconds 
                            ? Math.floor(device.last_status.system.uptime_seconds / 3600) + 'h'
                            : '-'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {filtered.length === 0 && (
              <div className="text-center py-16 px-6">
                <div className="max-w-md mx-auto p-8 border-2 border-dashed border-neutral-300 dark:border-neutral-700 rounded-2xl">
                  <p className="text-sm text-neutral-600 dark:text-neutral-400 mb-4">
                    {devices.length === 0 
                      ? 'No devices enrolled yet. Use scripts/enroll.sh to add devices.'
                      : 'No devices match this filter.'}
                  </p>
                  {devices.length === 0 && (
                    <button
                      onClick={() => setSettingsOpen(true)}
                      className="px-4 py-2 bg-accent hover:bg-accent/90 text-white text-sm font-medium rounded-lg transition-colors"
                    >
                      Open Settings
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </main>

      <DeviceDrawer 
        device={selectedDevice} 
        onClose={() => setSelectedDevice(null)} 
      />

      <SettingsModal 
        isOpen={settingsOpen} 
        onClose={() => setSettingsOpen(false)}
        onToast={setToast}
      />

      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  )
}

export default DeviceList
