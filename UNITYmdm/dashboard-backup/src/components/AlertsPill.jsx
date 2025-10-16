import { useState, useEffect, useRef } from 'react'
import { Bell, X } from 'lucide-react'

export default function AlertsPill({ count = 0 }) {
  const [isOpen, setIsOpen] = useState(false)
  const [alerts, setAlerts] = useState([])
  const panelRef = useRef(null)

  useEffect(() => {
    if (isOpen) {
      fetchAlerts()
    }
  }, [isOpen])

  useEffect(() => {
    function handleClickOutside(event) {
      if (panelRef.current && !panelRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }

    function handleEscape(event) {
      if (event.key === 'Escape') {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      document.addEventListener('keydown', handleEscape)
      return () => {
        document.removeEventListener('mousedown', handleClickOutside)
        document.removeEventListener('keydown', handleEscape)
      }
    }
  }, [isOpen])

  async function fetchAlerts() {
    try {
      const response = await fetch('/v1/devices')
      if (!response.ok) return
      const devices = await response.json()
      
      const recentAlerts = devices
        .filter(d => {
          if (!d.last_status) return false
          const battery = d.last_status.battery?.pct || 100
          const unityInstalled = d.last_status.app_versions?.unity?.installed || false
          const unityRunning = d.last_status.unity_running_signals?.has_service_notification || false
          return d.status === 'offline' || battery < 20 || !unityInstalled || !unityRunning
        })
        .map(d => {
          const issues = []
          if (d.status === 'offline') issues.push('Offline')
          if (d.last_status?.battery?.pct < 20) issues.push('Low battery')
          if (!d.last_status?.app_versions?.unity?.installed) issues.push('Unity not installed')
          if (!d.last_status?.unity_running_signals?.has_service_notification) issues.push('Unity down')
          
          return {
            alias: d.alias,
            type: issues.join(', '),
            timestamp: d.last_seen || new Date().toISOString()
          }
        })
        .slice(0, 10)
      
      setAlerts(recentAlerts)
    } catch (err) {
      console.error('Failed to fetch alerts:', err)
    }
  }

  const pillColor = count > 0 
    ? 'bg-accent/10 dark:bg-accent/20 text-accent border-accent/20 dark:border-accent/30' 
    : 'bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 border-neutral-200 dark:border-neutral-700'

  return (
    <div className="relative" ref={panelRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${pillColor}`}
        aria-label={`${count} active alerts`}
      >
        <Bell className="h-3.5 w-3.5" />
        <span>Alerts • {count}</span>
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 bg-white dark:bg-neutral-900 rounded-2xl shadow-xl overflow-hidden z-50">
          <div className="flex items-center justify-between px-4 py-3 border-b border-neutral-200 dark:border-neutral-800">
            <h3 className="font-semibold text-sm text-neutral-900 dark:text-white">Recent Alerts</h3>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-lg transition-colors"
              aria-label="Close"
            >
              <X className="h-4 w-4 text-neutral-600 dark:text-neutral-400" />
            </button>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {alerts.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-neutral-500 dark:text-neutral-400">
                No active alerts
              </div>
            ) : (
              <div className="divide-y divide-neutral-100 dark:divide-neutral-800">
                {alerts.map((alert, idx) => (
                  <div key={idx} className="px-4 py-3 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-neutral-900 dark:text-white truncate">
                          {alert.alias}
                        </p>
                        <p className="text-xs text-neutral-600 dark:text-neutral-400 mt-0.5">
                          {alert.type}
                        </p>
                      </div>
                      <time className="text-xs text-neutral-500 dark:text-neutral-500 whitespace-nowrap">
                        {new Date(alert.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
                      </time>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
