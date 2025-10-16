import { useEffect } from 'react'
import { X } from 'lucide-react'

export default function Toast({ message, onClose, duration = 2000 }) {
  useEffect(() => {
    const timer = setTimeout(onClose, duration)
    return () => clearTimeout(timer)
  }, [duration, onClose])

  return (
    <div className="fixed bottom-6 right-6 z-50 bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 px-4 py-3 rounded-xl shadow-lg flex items-center gap-3 animate-in fade-in slide-in-from-bottom-2 duration-300">
      <span className="text-sm font-medium">{message}</span>
      <button
        onClick={onClose}
        className="p-1 hover:bg-neutral-800 dark:hover:bg-neutral-200 rounded-lg transition-colors"
        aria-label="Close"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}
