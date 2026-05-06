import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Loader2, Play } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import {
  type JobRunLogEntry,
  type ScheduledJob,
  apiFetch,
} from "@/api/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

function JobRow({
  job,
  onAfterChange,
}: {
  job: ScheduledJob
  onAfterChange: () => void
}) {
  const [minutes, setMinutes] = useState(job.interval_minutes)
  const [enabled, setEnabled] = useState(job.enabled)

  useEffect(() => {
    setMinutes(job.interval_minutes)
    setEnabled(job.enabled)
  }, [job])

  const patchMut = useMutation({
    mutationFn: (body: { interval_minutes?: number; enabled?: boolean }) =>
      apiFetch<ScheduledJob>(`/api/scheduler/jobs/${job.id}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      toast.success(`Updated ${job.id}`)
      onAfterChange()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const runMut = useMutation({
    mutationFn: () =>
      apiFetch<{ ok: boolean }>(`/api/scheduler/jobs/${job.id}/run`, {
        method: "POST",
      }),
    onSuccess: () => {
      toast.success(`Ran ${job.id}`)
      onAfterChange()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <TableRow>
      <TableCell className="font-mono text-xs">{job.id}</TableCell>
      <TableCell>{job.name}</TableCell>
      <TableCell>
        <Input
          type="number"
          min={0}
          className="h-8 w-24 font-mono text-sm"
          value={minutes}
          onChange={(e) => setMinutes(Number.parseInt(e.target.value, 10) || 0)}
        />
      </TableCell>
      <TableCell>
        <input
          type="checkbox"
          className="h-4 w-4 accent-primary"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
        />
      </TableCell>
      <TableCell className="text-right">
        <div className="flex justify-end gap-2">
          <Button
            size="sm"
            variant="secondary"
            type="button"
            disabled={patchMut.isPending}
            onClick={() =>
              patchMut.mutate({
                interval_minutes: minutes,
                enabled,
              })
            }
          >
            Save
          </Button>
          <Button
            size="sm"
            variant="outline"
            type="button"
            disabled={runMut.isPending}
            onClick={() => runMut.mutate()}
          >
            <Play className="mr-1 h-3.5 w-3.5" />
            Run
          </Button>
        </div>
      </TableCell>
    </TableRow>
  )
}

export function SchedulerPage() {
  const qc = useQueryClient()
  const jobsQ = useQuery({
    queryKey: ["scheduler-jobs"],
    queryFn: () => apiFetch<ScheduledJob[]>("/api/scheduler/jobs"),
  })
  const runsQ = useQuery({
    queryKey: ["scheduler-job-runs"],
    queryFn: () => apiFetch<JobRunLogEntry[]>("/api/scheduler/job-runs"),
    refetchInterval: 10_000,
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["scheduler-jobs"] })
    qc.invalidateQueries({ queryKey: ["scheduler-job-runs"] })
  }

  if (jobsQ.error) {
    return (
      <p className="text-destructive text-sm">{(jobsQ.error as Error).message}</p>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">Scheduled jobs</h1>
      <p className="text-muted-foreground text-sm">
        Intervals in minutes; 0 disables scheduling for that job. Last 20 runs are kept in memory.
      </p>

      <Card>
        <CardHeader>
          <CardTitle>Jobs</CardTitle>
          <CardDescription>
            Aliyun sync and new-api channel tests register here. Changing values updates APScheduler
            immediately.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {jobsQ.isLoading ? (
            <Loader2 className="h-6 w-6 animate-spin" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Interval (min)</TableHead>
                  <TableHead>Enabled</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(jobsQ.data ?? []).map((j) => (
                  <JobRow key={j.id} job={j} onAfterChange={invalidate} />
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent job runs</CardTitle>
          <CardDescription>Newest first — at most 20 entries total.</CardDescription>
        </CardHeader>
        <CardContent>
          {runsQ.isLoading ? (
            <Loader2 className="h-6 w-6 animate-spin" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time</TableHead>
                  <TableHead>Job</TableHead>
                  <TableHead>OK</TableHead>
                  <TableHead>ms</TableHead>
                  <TableHead>Message</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(runsQ.data ?? []).length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="text-muted-foreground">
                      No runs yet.
                    </TableCell>
                  </TableRow>
                ) : (
                  runsQ.data!.map((r, i) => (
                    <TableRow key={`${r.at}-${i}`}>
                      <TableCell className="whitespace-nowrap text-xs">{r.at}</TableCell>
                      <TableCell className="font-mono text-xs">{r.job_id}</TableCell>
                      <TableCell>
                        {r.ok ? (
                          <Badge>yes</Badge>
                        ) : (
                          <Badge variant="destructive">no</Badge>
                        )}
                      </TableCell>
                      <TableCell className="font-mono text-xs">{r.duration_ms}</TableCell>
                      <TableCell className="max-w-md truncate text-xs text-muted-foreground">
                        {r.message || "—"}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
