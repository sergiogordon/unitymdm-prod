export default function SegmentedControl({ options, value, onChange }) {
  return (
    <div className="inline-flex bg-neutral-100 dark:bg-neutral-800 rounded-full p-1 gap-1">
      {options.map((option) => (
        <button
          key={option.value}
          onClick={() => onChange(option.value)}
          className={`px-4 py-2 rounded-full text-sm font-medium transition-all ${
            value === option.value
              ? 'bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white shadow-md transform translate-y-[-1px]'
              : 'text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
