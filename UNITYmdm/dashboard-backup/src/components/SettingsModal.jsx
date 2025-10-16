import { X, Send } from 'lucide-react'
import { useState, useEffect, useRef } from 'react'

export default function SettingsModal({ isOpen, onClose, onToast }) {
  const modalRef = useRef(null)
  const [refreshInterval, setRefreshInterval] = useState(() => {
    return localStorage.getItem('refreshInterval') || '10'
  })
  const [showAlertBadges, setShowAlertBadges] = useState(() => {
    return localStorage.getItem('showAlertBadges') !== 'false'
  })
  const [compactView, setCompactView] = useState(() => {
    return localStorage.getItem('compactView') === 'true'
  })
  const [testAlertStatus, setTestAlertStatus] = useState(null)
  
  const singleDeviceScript = `cd scripts
export SERVER_URL="https://your-replit-app.repl.co"
export ADMIN_KEY="your-admin-key"
./enroll_device.sh "RackA-07" "com.unity.app"`

  const bulkEnrollScript = `cd scripts
export SERVER_URL="https://your-replit-app.repl.co"
export ADMIN_KEY="your-admin-key"
# Create devices.csv first
./bulk_enroll.sh`

  const copySingleDevice = () => {
    navigator.clipboard.writeText(singleDeviceScript)
    if (onToast) onToast('Single-device command copied!')
  }

  const copyBulkEnroll = () => {
    navigator.clipboard.writeText(bulkEnrollScript)
    if (onToast) onToast('Bulk enrollment command copied!')
  }

  const sendTestAlert = async () => {
    try {
      setTestAlertStatus('sending')
      const response = await fetch('/v1/devices')
      if (!response.ok) throw new Error('Failed to test alert')
      
      setTestAlertStatus('sent')
      if (onToast) onToast('Test alert sent successfully!')
      setTimeout(() => setTestAlertStatus(null), 3000)
    } catch (err) {
      setTestAlertStatus('error')
      if (onToast) onToast('Failed to send test alert')
      setTimeout(() => setTestAlertStatus(null), 3000)
    }
  }

  useEffect(() => {
    localStorage.setItem('refreshInterval', refreshInterval)
    localStorage.setItem('showAlertBadges', showAlertBadges.toString())
    localStorage.setItem('compactView', compactView.toString())
    window.dispatchEvent(new CustomEvent('settingsChanged', { 
      detail: { refreshInterval, showAlertBadges, compactView } 
    }))
  }, [refreshInterval, showAlertBadges, compactView])

  useEffect(() => {
    if (!isOpen) return

    document.body.style.overflow = 'hidden'

    const handleEscape = (e) => {
      if (e.key === 'Escape') onClose()
    }

    const handleTab = (e) => {
      if (e.key !== 'Tab') return
      const focusableElements = modalRef.current?.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
      if (!focusableElements || focusableElements.length === 0) return

      const firstElement = focusableElements[0]
      const lastElement = focusableElements[focusableElements.length - 1]

      if (e.shiftKey && document.activeElement === firstElement) {
        lastElement.focus()
        e.preventDefault()
      } else if (!e.shiftKey && document.activeElement === lastElement) {
        firstElement.focus()
        e.preventDefault()
      }
    }

    document.addEventListener('keydown', handleEscape)
    document.addEventListener('keydown', handleTab)

    return () => {
      document.body.style.overflow = ''
      document.removeEventListener('keydown', handleEscape)
      document.removeEventListener('keydown', handleTab)
    }
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <>
      <div 
        className="fixed inset-0 bg-black/30 dark:bg-black/50 z-40 transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />
      <div 
        ref={modalRef}
        className="fixed inset-y-0 right-0 z-50 w-full sm:w-[480px] bg-white dark:bg-neutral-900 shadow-2xl flex flex-col"
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
      >
        <div className="sticky top-0 bg-white dark:bg-neutral-900 border-b border-neutral-200 dark:border-neutral-800 px-6 py-4 flex items-center justify-between z-10">
          <h2 id="drawer-title" className="text-xl font-semibold tracking-tight text-neutral-900 dark:text-white">Settings</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-lg transition-colors"
            aria-label="Close settings"
          >
            <X className="h-5 w-5 text-neutral-500" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="p-6 space-y-6">
            <section>
              <h3 className="text-lg font-semibold tracking-tight text-neutral-900 dark:text-white mb-3">
                Display Preferences
              </h3>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium text-neutral-900 dark:text-white">Refresh Interval</div>
                    <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                      How often to update device status
                    </div>
                  </div>
                  <select
                    value={refreshInterval}
                    onChange={(e) => setRefreshInterval(e.target.value)}
                    className="px-3 py-2 bg-neutral-100 dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-700 rounded-lg text-sm text-neutral-900 dark:text-white focus:ring-2 focus:ring-accent focus:border-transparent outline-none"
                  >
                    <option value="5">5 seconds</option>
                    <option value="10">10 seconds</option>
                    <option value="30">30 seconds</option>
                    <option value="60">60 seconds</option>
                  </select>
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium text-neutral-900 dark:text-white">Show Alert Badges</div>
                    <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                      Display running/down badges on Unity status
                    </div>
                  </div>
                  <button
                    onClick={() => setShowAlertBadges(!showAlertBadges)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      showAlertBadges ? 'bg-accent' : 'bg-neutral-300 dark:bg-neutral-700'
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        showAlertBadges ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium text-neutral-900 dark:text-white">Compact View</div>
                    <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                      Reduce spacing for more devices on screen
                    </div>
                  </div>
                  <button
                    onClick={() => setCompactView(!compactView)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      compactView ? 'bg-accent' : 'bg-neutral-300 dark:bg-neutral-700'
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        compactView ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>
              </div>
            </section>

            <section>
              <h3 className="text-lg font-semibold tracking-tight text-neutral-900 dark:text-white mb-3">
                Enrollment
              </h3>
              <p className="text-sm text-neutral-600 dark:text-neutral-400 mb-3">
                Use ADB commands to enroll devices. Set SERVER_URL and ADMIN_KEY environment variables first.
              </p>
              <div className="space-y-3">
                <div>
                  <div className="text-xs font-medium text-neutral-700 dark:text-neutral-300 mb-2">Single Device</div>
                  <div className="relative">
                    <pre className="bg-neutral-100 dark:bg-neutral-800 rounded-xl p-3 text-xs font-mono overflow-x-auto">
                      <code className="text-neutral-800 dark:text-neutral-200">{singleDeviceScript}</code>
                    </pre>
                    <button
                      onClick={copySingleDevice}
                      className="absolute top-2 right-2 px-3 py-1.5 bg-white dark:bg-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-600 rounded-lg text-xs font-medium text-neutral-700 dark:text-neutral-200 transition-colors shadow-sm"
                    >
                      Copy
                    </button>
                  </div>
                </div>
                <div>
                  <div className="text-xs font-medium text-neutral-700 dark:text-neutral-300 mb-2">Bulk Enrollment</div>
                  <div className="relative">
                    <pre className="bg-neutral-100 dark:bg-neutral-800 rounded-xl p-3 text-xs font-mono overflow-x-auto">
                      <code className="text-neutral-800 dark:text-neutral-200">{bulkEnrollScript}</code>
                    </pre>
                    <button
                      onClick={copyBulkEnroll}
                      className="absolute top-2 right-2 px-3 py-1.5 bg-white dark:bg-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-600 rounded-lg text-xs font-medium text-neutral-700 dark:text-neutral-200 transition-colors shadow-sm"
                    >
                      Copy
                    </button>
                  </div>
                </div>
              </div>
            </section>

            <section>
              <h3 className="text-lg font-semibold tracking-tight text-neutral-900 dark:text-white mb-3">
                Discord Alerts
              </h3>
              <p className="text-sm text-neutral-600 dark:text-neutral-400 mb-3">
                Test your Discord webhook integration by sending a test alert.
              </p>
              <button
                onClick={sendTestAlert}
                disabled={testAlertStatus === 'sending'}
                className="flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent/90 disabled:bg-neutral-300 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors"
              >
                <Send className="h-4 w-4" />
                {testAlertStatus === 'sending' ? 'Sending...' : 'Send Test Alert'}
              </button>
              {testAlertStatus === 'sent' && (
                <p className="mt-2 text-xs text-emerald-600 dark:text-emerald-400">
                  ✓ Test alert sent successfully
                </p>
              )}
              {testAlertStatus === 'error' && (
                <p className="mt-2 text-xs text-rose-600 dark:text-rose-400">
                  ✗ Failed to send test alert
                </p>
              )}
            </section>

            <section>
              <h3 className="text-lg font-semibold tracking-tight text-neutral-900 dark:text-white mb-3">
                Android Permissions
              </h3>
              <p className="text-sm text-neutral-600 dark:text-neutral-400 mb-2">
                After enrollment, grant these permissions on each device:
              </p>
              <ol className="list-decimal list-inside space-y-1 text-sm text-neutral-600 dark:text-neutral-400">
                <li>Settings → Apps → Special access → Usage access → Unity MDM</li>
                <li>Settings → Apps → Special access → Notification access → Unity MDM</li>
              </ol>
            </section>

            <section>
              <h3 className="text-lg font-semibold tracking-tight text-neutral-900 dark:text-white mb-3">
                System Configuration
              </h3>
              <div className="space-y-3">
                <div className="bg-neutral-50 dark:bg-neutral-800 rounded-xl p-4">
                  <div className="text-sm font-medium text-neutral-700 dark:text-neutral-300">Offline Threshold</div>
                  <div className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">10 minutes (600 seconds)</div>
                </div>
                <div className="bg-neutral-50 dark:bg-neutral-800 rounded-xl p-4">
                  <div className="text-sm font-medium text-neutral-700 dark:text-neutral-300">Heartbeat Interval</div>
                  <div className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">2 minutes (120 seconds)</div>
                </div>
              </div>
            </section>

            <section>
              <h3 className="text-lg font-semibold tracking-tight text-neutral-900 dark:text-white mb-3">
                Alert Conditions
              </h3>
              <ul className="space-y-2 text-sm text-neutral-600 dark:text-neutral-400">
                <li className="flex items-start gap-2">
                  <span className="text-rose-500 mt-1">•</span>
                  <span>Device offline ({">"} 10 minutes)</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-amber-500 mt-1">•</span>
                  <span>Unity app not installed</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-amber-500 mt-1">•</span>
                  <span>Unity app not running</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-amber-500 mt-1">•</span>
                  <span>Low battery (&lt; 20%)</span>
                </li>
              </ul>
            </section>
          </div>
        </div>
      </div>
    </>
  )
}
