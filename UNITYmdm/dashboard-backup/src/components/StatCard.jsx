export default function StatCard({ label, value, semanticColor = null, compact = false }) {
  const getValueColor = () => {
    if (semanticColor && value > 0) {
      if (semanticColor === 'red') return 'text-rose-600 dark:text-rose-500'
      if (semanticColor === 'amber') return 'text-amber-600 dark:text-amber-500'
    }
    return 'text-neutral-900 dark:text-white'
  }

  return (
    <div className={`bg-white dark:bg-neutral-900 rounded-2xl ${compact ? 'p-4' : 'p-6'} shadow-sm`}>
      <div className={`${compact ? 'text-2xl' : 'text-3xl'} font-semibold tracking-tight ${getValueColor()}`}>
        {value}
      </div>
      <div className={`${compact ? 'text-xs mt-1' : 'text-sm mt-2'} font-medium text-neutral-500 dark:text-neutral-400`}>
        {label}
      </div>
    </div>
  )
}
