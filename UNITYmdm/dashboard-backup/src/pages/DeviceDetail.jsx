import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Circle } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

function DeviceDetail() {
  const { deviceId } = useParams()
  const [device, setDevice] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchDevice()
    const interval = setInterval(fetchDevice, 10000)
    return () => clearInterval(interval)
  }, [deviceId])

  async function fetchDevice() {
    try {
      const response = await fetch(`/v1/devices/${deviceId}`)
      const data = await response.json()
      setDevice(data)
      setLoading(false)
    } catch (error) {
      console.error('Failed to fetch device:', error)
      setLoading(false)
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-screen">Loading...</div>
  }

  if (!device) {
    return <div className="flex items-center justify-center h-screen">Device not found</div>
  }

  const status = device.last_status || {}
  const isOnline = device.last_seen && (new Date() - new Date(device.last_seen)) < 240000

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Link to="/" className="inline-flex items-center gap-2 text-blue-600 dark:text-blue-400 hover:underline mb-6">
          <ArrowLeft className="h-4 w-4" />
          Back to devices
        </Link>

        <div className="flex items-center gap-4 mb-8">
          <Circle className={`h-4 w-4 fill-current ${isOnline ? 'text-green-500' : 'text-red-500'}`} />
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">{device.alias}</h1>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Device Info</h2>
            <dl className="space-y-2">
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Device ID</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-300 font-mono">{device.id}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Last Seen</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-300">
                  {device.last_seen ? formatDistanceToNow(new Date(device.last_seen), { addSuffix: true }) : 'Never'}
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Created At</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-300">
                  {device.created_at ? new Date(device.created_at).toLocaleString() : '-'}
                </dd>
              </div>
            </dl>
          </div>

          <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">System</h2>
            <dl className="space-y-2">
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Model</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-300">
                  {status.system?.manufacturer} {status.system?.model}
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Android Version</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-300">{status.system?.android_version}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Security Patch</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-300">{status.system?.patch_level}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Uptime</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-300">
                  {status.system?.uptime_seconds 
                    ? `${Math.floor(status.system.uptime_seconds / 3600)}h ${Math.floor((status.system.uptime_seconds % 3600) / 60)}m`
                    : '-'}
                </dd>
              </div>
            </dl>
          </div>

          <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Unity App</h2>
            <dl className="space-y-2">
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Installed</dt>
                <dd className="mt-1 text-sm">
                  {status.app_versions?.unity?.installed ? (
                    <span className="text-green-600">Yes</span>
                  ) : (
                    <span className="text-red-600">No</span>
                  )}
                </dd>
              </div>
              {status.app_versions?.unity?.installed && (
                <>
                  <div>
                    <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Version</dt>
                    <dd className="mt-1 text-sm text-gray-900 dark:text-gray-300">
                      {status.app_versions.unity.version_name} ({status.app_versions.unity.version_code})
                    </dd>
                  </div>
                  <div>
                    <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Running</dt>
                    <dd className="mt-1 text-sm">
                      {status.unity_running_signals?.has_service_notification ? (
                        <span className="text-green-600">Yes</span>
                      ) : (
                        <span className="text-yellow-600">Unknown/No</span>
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Last Foreground</dt>
                    <dd className="mt-1 text-sm text-gray-900 dark:text-gray-300">
                      {status.unity_running_signals?.foreground_recent_seconds !== null
                        ? `${status.unity_running_signals.foreground_recent_seconds}s ago`
                        : 'Unknown'}
                    </dd>
                  </div>
                </>
              )}
            </dl>
          </div>

          <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Hardware Status</h2>
            <dl className="space-y-2">
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Battery</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-300">
                  {status.battery?.pct}% ({status.battery?.charging ? 'Charging' : 'Not charging'})
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Temperature</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-300">{status.battery?.temperature_c}°C</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">RAM</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-300">
                  {status.memory?.avail_ram_mb}MB / {status.memory?.total_ram_mb}MB available
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">RAM Pressure</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-300">{status.memory?.pressure_pct}%</dd>
              </div>
            </dl>
          </div>

          <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Network</h2>
            <dl className="space-y-2">
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Transport</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-300">{status.network?.transport || '-'}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">SSID</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-300">{status.network?.ssid || '-'}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Carrier</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-300">{status.network?.carrier || '-'}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">IP Address</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-300 font-mono">{status.network?.ip || '-'}</dd>
              </div>
            </dl>
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Full Heartbeat JSON</h2>
          <pre className="bg-gray-100 dark:bg-gray-900 p-4 rounded text-xs overflow-auto max-h-96">
            {JSON.stringify(status, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  )
}

export default DeviceDetail
