import { useQuery } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"
import { useState } from "react"
import { type AppLogEntry, apiFetch } from "@/api/client"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

export function LogsPage() {
  const [limit, setLimit] = useState(500)
  const [level, setLevel] = useState("")

  const logsQ = useQuery({
    queryKey: ["app-logs", limit, level],
    queryFn: () => {
      const q = new URLSearchParams()
      q.set("limit", String(limit))
      if (level.trim()) q.set("level", level.trim().toUpperCase())
      return apiFetch<AppLogEntry[]>(`/api/logs/?${q.toString()}`)
    },
    refetchInterval: 15_000,
  })

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Application logs</h1>
      <p className="text-muted-foreground text-sm">
        Tail of the server log file on disk (newest first), up to 2000 lines per request.
      </p>

      <Card>
        <CardHeader>
          <CardTitle>Query</CardTitle>
          <CardDescription>Filter by log level (optional). Limit 1–2000.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-4">
          <div className="grid gap-2">
            <Label className="text-xs">Limit</Label>
            <Input
              className="h-9 w-28 font-mono text-sm"
              type="number"
              min={1}
              max={2000}
              value={limit}
              onChange={(e) =>
                setLimit(
                  Math.min(2000, Math.max(1, Number.parseInt(e.target.value, 10) || 500)),
                )
              }
            />
          </div>
          <div className="grid gap-2">
            <Label className="text-xs">Level</Label>
            <Input
              className="h-9 w-32 font-mono text-sm"
              placeholder="INFO, WARNING…"
              value={level}
              onChange={(e) => setLevel(e.target.value)}
            />
          </div>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => logsQ.refetch()}
          >
            Refresh
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          {logsQ.isLoading ? (
            <Loader2 className="h-6 w-6 animate-spin" />
          ) : logsQ.error ? (
            <p className="text-destructive text-sm">{(logsQ.error as Error).message}</p>
          ) : (
            <div className="max-h-[min(70vh,720px)] overflow-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-44">Time</TableHead>
                    <TableHead className="w-20">Level</TableHead>
                    <TableHead className="w-40">Logger</TableHead>
                    <TableHead>Message</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(logsQ.data ?? []).map((row, i) => (
                    <TableRow key={`${row.ts}-${i}`}>
                      <TableCell className="align-top font-mono text-[11px] whitespace-nowrap">
                        {row.ts}
                      </TableCell>
                      <TableCell className="align-top text-xs">{row.level}</TableCell>
                      <TableCell className="align-top font-mono text-[11px]">
                        {row.logger}
                      </TableCell>
                      <TableCell className="max-w-[min(100vw,48rem)] break-all font-mono text-[11px] leading-snug">
                        {row.message}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
