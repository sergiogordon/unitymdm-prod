import { useEffect, useState } from 'react'

export default function RefreshIndicator({ lastUpdate }) {
  const [timeAgo, setTimeAgo] = useState('just now')
  const [isPulsing, setIsPulsing] = useState(false)

  useEffect(() => {
    if (lastUpdate) {
      setIsPulsing(true)
      const timeout = setTimeout(() => setIsPulsing(false), 300)
      return () => clearTimeout(timeout)
    }
  }, [lastUpdate])

  useEffect(() => {
    const interval = setInterval(() => {
      if (!lastUpdate) {
        setTimeAgo('never')
        return
      }
      
      const seconds = Math.floor((Date.now() - lastUpdate) / 1000)
      if (seconds < 10) setTimeAgo('just now')
      else if (seconds < 60) setTimeAgo(`${seconds}s ago`)
      else setTimeAgo(`${Math.floor(seconds / 60)}m ago`)
    }, 1000)
    
    return () => clearInterval(interval)
  }, [lastUpdate])

  return (
    <div className="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400" role="status" aria-live="polite">
      <div className="flex items-center gap-1.5">
        <div className={`w-1.5 h-1.5 rounded-full bg-emerald-500 ${isPulsing ? 'animate-ping' : ''}`} />
        <span className={`text-xs transition-opacity duration-300 ${isPulsing ? 'opacity-100' : 'opacity-70'}`}>
          Updated • {timeAgo}
        </span>
      </div>
    </div>
  )
}
