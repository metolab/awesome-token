import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { Toaster } from "@/components/ui/sonner"
import { Layout } from "@/components/Layout"
import { AliyunAccountsPage } from "@/pages/AliyunAccounts"
import { LogsPage } from "@/pages/LogsPage"
import { NewApiPage } from "@/pages/NewApiPage"
import { SchedulerPage } from "@/pages/SchedulerPage"

const qc = new QueryClient({
  defaultOptions: {
    queries: { retry: false, refetchOnWindowFocus: false },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<AliyunAccountsPage />} />
            <Route path="/new-api" element={<NewApiPage />} />
            <Route path="/scheduler" element={<SchedulerPage />} />
            <Route path="/logs" element={<LogsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster richColors position="top-center" />
    </QueryClientProvider>
  )
}
