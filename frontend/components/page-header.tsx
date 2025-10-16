import type React from "react"
interface PageHeaderProps {
  title: string
  description?: string
  icon?: React.ReactNode
}

export function PageHeader({ title, description, icon }: PageHeaderProps) {
  return (
    <div className="mb-8">
      <div className="flex items-center gap-3">
        {icon && <div className="text-muted-foreground">{icon}</div>}
        <h1 className="text-balance text-3xl font-semibold tracking-tight text-foreground">{title}</h1>
      </div>
      {description && <p className="mt-2 text-pretty text-muted-foreground">{description}</p>}
    </div>
  )
}
