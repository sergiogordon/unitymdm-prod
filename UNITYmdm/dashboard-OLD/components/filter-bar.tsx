"use client"

import type { FilterType } from "@/lib/mock-data"

interface FilterBarProps {
  selected: FilterType
  onSelect: (filter: FilterType) => void
}

const filters: { value: FilterType; label: string }[] = [
  { value: "all", label: "All" },
  { value: "offline", label: "Offline" },
  { value: "unity-down", label: "Unity Down" },
  { value: "low-battery", label: "Low Battery" },
  { value: "wrong-version", label: "Wrong Version" },
]

export function FilterBar({ selected, onSelect }: FilterBarProps) {
  return (
    <div className="sticky top-[60px] z-40 mb-6 flex justify-center border-b border-border/40 bg-background/80 py-4 backdrop-blur-xl">
      <div className="inline-flex rounded-lg bg-muted p-1">
        {filters.map((filter) => (
          <button
            key={filter.value}
            onClick={() => onSelect(filter.value)}
            className={`rounded-md px-4 py-2 text-sm font-medium transition-all ${
              selected === filter.value
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {filter.label}
          </button>
        ))}
      </div>
    </div>
  )
}
