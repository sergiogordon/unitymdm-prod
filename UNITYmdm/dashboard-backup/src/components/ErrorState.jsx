export default function ErrorState({ onRetry }) {
  return (
    <div className="bg-white dark:bg-neutral-900 rounded-2xl shadow-sm border border-rose-200 dark:border-rose-900/50 p-8">
      <div className="text-center space-y-4">
        <div className="inline-flex items-center justify-center w-12 h-12 bg-rose-100 dark:bg-rose-900/30 rounded-full">
          <svg className="w-6 h-6 text-rose-600 dark:text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <div>
          <h3 className="text-lg font-semibold text-neutral-900 dark:text-white">
            Failed to load devices
          </h3>
          <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">
            There was a problem connecting to the server. Please check your connection and try again.
          </p>
        </div>
        <button
          onClick={onRetry}
          className="inline-flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent/90 text-white rounded-lg font-medium transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Retry
        </button>
      </div>
    </div>
  )
}
