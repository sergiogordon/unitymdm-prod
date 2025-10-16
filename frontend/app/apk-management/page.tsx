"use client"

import { useState, useEffect } from "react"
import { Header } from "@/components/header"
import { PageHeader } from "@/components/page-header"
import { SettingsDrawer } from "@/components/settings-drawer"
import { Package, Upload, Download, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"

export default function ApkManagementPage() {
  const [isDark, setIsDark] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(Date.now())
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add("dark")
    } else {
      document.documentElement.classList.remove("dark")
    }
  }, [isDark])

  const handleRefresh = () => {
    setLastUpdated(Date.now())
  }

  const apkFiles = [
    { name: "Unity-v1.2.0.apk", version: "1.2.0", size: "24.5 MB", uploaded: "2 days ago" },
    { name: "Unity-v1.1.5.apk", version: "1.1.5", size: "23.8 MB", uploaded: "1 week ago" },
  ]

  return (
    <div className="min-h-screen">
      <Header
        lastUpdated={lastUpdated}
        alertCount={0}
        isDark={isDark}
        onToggleDark={() => setIsDark(!isDark)}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onRefresh={handleRefresh}
      />

      <main className="mx-auto max-w-[1280px] px-6 pb-12 pt-[84px] md:px-8">
        <PageHeader
          icon={<Package className="h-8 w-8" />}
          title="APK Management"
          description="Upload, manage, and deploy Android application packages to your device fleet."
        />

        <div className="space-y-6">
          <Card className="rounded-2xl border border-border bg-card p-6 shadow-sm">
            <div className="mb-6 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-card-foreground">Available APK Files</h2>
              <Button className="gap-2">
                <Upload className="h-4 w-4" />
                Upload APK
              </Button>
            </div>

            <div className="overflow-hidden rounded-lg border border-border">
              <table className="w-full">
                <thead className="border-b border-border bg-muted/50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">File Name</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">Version</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">Size</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">Uploaded</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold text-muted-foreground">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {apkFiles.map((apk, index) => (
                    <tr key={index} className="border-b border-border last:border-0">
                      <td className="px-4 py-3 font-mono text-sm text-card-foreground">{apk.name}</td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">{apk.version}</td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">{apk.size}</td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">{apk.uploaded}</td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <Button variant="ghost" size="sm">
                            <Download className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="sm">
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      </main>

      <SettingsDrawer isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </div>
  )
}
