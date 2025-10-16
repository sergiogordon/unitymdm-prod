interface KpiTilesProps {
  total: number
  online: number
  offline: number
  alerts: number
  onAlertsClick?: () => void
}

export function KpiTiles({ total, online, offline, alerts, onAlertsClick }: KpiTilesProps) {
  return (
    <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <div className="rounded-xl bg-card p-6 shadow-sm">
        <div className="text-3xl font-semibold tracking-tight">{total}</div>
        <div className="mt-1 text-sm text-muted-foreground">Total Devices</div>
      </div>

      <div className="rounded-xl bg-card p-6 shadow-sm">
        <div className="text-3xl font-semibold tracking-tight text-status-online">{online}</div>
        <div className="mt-1 text-sm text-muted-foreground">Online</div>
      </div>

      <div className="rounded-xl bg-card p-6 shadow-sm">
        <div className={`text-3xl font-semibold tracking-tight ${offline > 0 ? "text-status-offline" : ""}`}>
          {offline}
        </div>
        <div className="mt-1 text-sm text-muted-foreground">Offline</div>
      </div>

      <button
        onClick={onAlertsClick}
        className="rounded-xl bg-card p-6 text-left shadow-sm transition-colors hover:bg-muted/30 disabled:cursor-default disabled:hover:bg-card"
        disabled={alerts === 0}
      >
        <div className={`text-3xl font-semibold tracking-tight ${alerts > 0 ? "text-status-warning" : ""}`}>
          {alerts}
        </div>
        <div className="mt-1 text-sm text-muted-foreground">
          Active Alerts {alerts > 0 && <span className="ml-1 text-xs">(click to view)</span>}
        </div>
      </button>
    </div>
  )
}
