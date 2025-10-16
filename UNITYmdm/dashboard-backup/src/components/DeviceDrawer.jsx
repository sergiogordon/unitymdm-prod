import { X } from 'lucide-react'
import { useEffect } from 'react'
import { formatDistanceToNow } from 'date-fns'

export default function DeviceDrawer({ device, onClose }) {
  useEffect(() => {
    const handleEsc = (e) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [onClose])

  if (!device) return null

  const getStatusInfo = () => {
    if (device.status === 'offline') {
      return { color: 'rose', text: 'Offline' }
    }
    if (!device.last_status) return { color: 'neutral', text: 'Unknown' }
    
    const battery = device.last_status.battery?.pct || 100
    const unityInstalled = device.last_status.app_versions?.unity?.installed || false
    const unityRunning = device.last_status.unity_running_signals?.has_service_notification || false
    
    if (battery < 20 || !unityInstalled || !unityRunning) {
      return { color: 'amber', text: 'Alert' }
    }
    
    return { color: 'emerald', text: 'Online' }
  }

  const statusInfo = getStatusInfo()
  const statusColors = {
    emerald: 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400',
    rose: 'bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-400',
    amber: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400',
    neutral: 'bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-400',
  }

  return (
    <>
      <div 
        className="fixed inset-0 bg-black/30 dark:bg-black/50 z-40 transition-opacity"
        onClick={onClose}
      />
      <div className="fixed inset-y-0 right-0 w-full sm:w-[440px] bg-white dark:bg-neutral-900 z-50 shadow-2xl overflow-y-auto">
        <div className="sticky top-0 bg-white/95 dark:bg-neutral-900/95 backdrop-blur-md border-b border-neutral-200 dark:border-neutral-800 px-6 py-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold tracking-tight text-neutral-900 dark:text-white">{device.alias}</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-lg transition-colors"
            aria-label="Close details"
          >
            <X className="h-5 w-5 text-neutral-500" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          <div className="bg-neutral-50 dark:bg-neutral-800 rounded-2xl p-6 space-y-4">
            <div>
              <div className="text-sm font-medium text-neutral-500 dark:text-neutral-400">Status</div>
              <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium mt-2 ${statusColors[statusInfo.color]}`}>
                <div className={`w-2 h-2 rounded-full bg-current`} />
                {statusInfo.text}
              </div>
            </div>

            <div>
              <div className="text-sm font-medium text-neutral-500 dark:text-neutral-400">Last Seen</div>
              <div className="text-base font-medium text-neutral-900 dark:text-white mt-1">
                {device.last_seen ? formatDistanceToNow(new Date(device.last_seen), { addSuffix: true }) : 'Never'}
              </div>
            </div>

            {device.last_status && (
              <>
                <div>
                  <div className="text-sm font-medium text-neutral-500 dark:text-neutral-400">Battery</div>
                  <div className="text-base font-medium text-neutral-900 dark:text-white mt-1">
                    {device.last_status.battery?.pct ?? '-'}%
                    {device.last_status.battery?.charging && (
                      <span className="text-sm text-neutral-500 ml-2">(charging)</span>
                    )}
                  </div>
                </div>

                <div>
                  <div className="text-sm font-medium text-neutral-500 dark:text-neutral-400">Network</div>
                  <div className="text-base font-medium text-neutral-900 dark:text-white mt-1">
                    {device.last_status.network?.transport === 'wifi' 
                      ? device.last_status.network?.wifi_ssid || 'WiFi'
                      : device.last_status.network?.carrier_name || 'Cellular'}
                  </div>
                </div>

                <div>
                  <div className="text-sm font-medium text-neutral-500 dark:text-neutral-400">Unity App</div>
                  <div className="text-base font-medium text-neutral-900 dark:text-white mt-1">
                    {device.last_status.app_versions?.unity?.installed ? (
                      <div className="flex items-center gap-2">
                        <span>v{device.last_status.app_versions.unity.version_name}</span>
                        {localStorage.getItem('showAlertBadges') !== 'false' && device.last_status.unity_running_signals?.has_service_notification && (
                          <span className="px-2 py-0.5 bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 text-xs rounded-full">
                            running
                          </span>
                        )}
                      </div>
                    ) : (
                      <span className="text-rose-600 dark:text-rose-400">Not installed</span>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>

          <div>
            <h3 className="text-sm font-semibold tracking-tight text-neutral-900 dark:text-white mb-3">
              Last Heartbeat
            </h3>
            <pre className="bg-neutral-100 dark:bg-neutral-800 rounded-xl p-4 text-xs font-mono overflow-x-auto border border-neutral-200 dark:border-neutral-700">
              <code className="text-neutral-800 dark:text-neutral-200">
                {JSON.stringify(device.last_status || {}, null, 2)}
              </code>
            </pre>
          </div>
        </div>
      </div>
    </>
  )
}
