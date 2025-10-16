export default function LoadingSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="bg-neutral-100 dark:bg-neutral-800 rounded-xl h-16" />
      ))}
    </div>
  )
}
