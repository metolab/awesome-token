import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { lazy, Suspense } from "react"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { Toaster } from "@/components/ui/sonner"
import { Layout } from "@/components/Layout"

const AliyunAccountsPage = lazy(async () => {
  const mod = await import("@/pages/AliyunAccounts")
  return { default: mod.AliyunAccountsPage }
})

const NewApiPage = lazy(async () => {
  const mod = await import("@/pages/NewApiPage")
  return { default: mod.NewApiPage }
})

const SchedulerPage = lazy(async () => {
  const mod = await import("@/pages/SchedulerPage")
  return { default: mod.SchedulerPage }
})

const LogsPage = lazy(async () => {
  const mod = await import("@/pages/LogsPage")
  return { default: mod.LogsPage }
})

const qc = new QueryClient({
  defaultOptions: {
    queries: { retry: false, refetchOnWindowFocus: false },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Suspense
          fallback={
            <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
              Loading...
            </div>
          }
        >
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<AliyunAccountsPage />} />
              <Route path="/new-api" element={<NewApiPage />} />
              <Route path="/scheduler" element={<SchedulerPage />} />
              <Route path="/logs" element={<LogsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
      <Toaster richColors position="top-center" />
    </QueryClientProvider>
  )
}
