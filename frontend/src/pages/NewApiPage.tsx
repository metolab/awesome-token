import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Eye, Loader2, RefreshCw } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import {
  type ChannelDetailResponse,
  type ChannelRow,
  type NewApiConfig,
  apiFetch,
} from "@/api/client"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"

const DEFAULT_NEWAPI_TEMPLATE_JSON = `{
  "name_template": "Aliyun {username}",
  "channel": {}
}`

function statusLabel(s: number | null | undefined) {
  if (s === 1) return <Badge>Enabled</Badge>
  if (s === 2) return <Badge variant="secondary">Disabled</Badge>
  if (s === 3) return <Badge variant="destructive">Auto-disabled</Badge>
  return <Badge variant="outline">Unknown</Badge>
}

function formatChannelFieldValue(v: unknown): string {
  if (v === null || v === undefined) return "—"
  if (typeof v === "object") return JSON.stringify(v)
  return String(v)
}

function ChannelInspectorDialog({
  channelId,
  open,
  onOpenChange,
}: {
  channelId: number | null
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const detailQ = useQuery({
    queryKey: ["newapi-channel-detail", channelId],
    queryFn: () =>
      apiFetch<ChannelDetailResponse>(
        `/api/newapi/channels/${channelId}/detail`,
      ),
    enabled: open && channelId != null && channelId > 0,
    staleTime: 0,
  })

  const payload = detailQ.data?.body
  const inner =
    payload &&
    typeof payload === "object" &&
    payload !== null &&
    "data" in payload
      ? (payload as Record<string, unknown>).data
      : null
  const fieldEntries =
    inner !== null &&
    typeof inner === "object" &&
    !Array.isArray(inner)
      ? Object.entries(inner as Record<string, unknown>).sort(([a], [b]) =>
          a.localeCompare(b),
        )
      : []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90vh] max-w-3xl flex-col overflow-hidden sm:max-w-3xl">
        <DialogHeader className="shrink-0">
          <DialogTitle>
            Channel {channelId != null ? `#${channelId}` : ""}
          </DialogTitle>
          <p className="text-muted-foreground text-sm font-normal">
            Live GET from new-api <code className="text-xs">/api/channel/{"{id}"}</code> — full
            response below.
          </p>
        </DialogHeader>

        {detailQ.isLoading ? (
          <div className="flex justify-center py-10">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : detailQ.error ? (
          <p className="text-destructive text-sm">
            {(detailQ.error as Error).message}
          </p>
        ) : payload ? (
          <div className="flex min-h-0 w-full flex-1 flex-col overflow-hidden">
            <Tabs
              defaultValue="fields"
              className="flex min-h-0 w-full flex-1 flex-col gap-0"
            >
            <TabsList className="grid w-full shrink-0 grid-cols-2">
              <TabsTrigger value="fields">Fields</TabsTrigger>
              <TabsTrigger value="raw">Raw JSON</TabsTrigger>
            </TabsList>
            <TabsContent
              value="fields"
              className="mt-3 min-h-0 flex-1 space-y-3 overflow-hidden"
            >
              {"success" in payload && payload.success === false ? (
                <Alert variant="destructive">
                  <AlertTitle>new-api reported failure</AlertTitle>
                  <AlertDescription>
                    {String(
                      (payload as Record<string, unknown>).message ?? "unknown",
                    )}
                  </AlertDescription>
                </Alert>
              ) : null}
              {fieldEntries.length === 0 ? (
                <p className="text-muted-foreground text-sm">
                  No <code className="text-xs">data</code> object in the response, or it is not a
                  plain object. Use the Raw JSON tab.
                </p>
              ) : (
                <div className="max-h-[min(55vh,520px)] overflow-y-auto overscroll-contain rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-[40%]">Field</TableHead>
                        <TableHead>Value</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {fieldEntries.map(([k, v]) => (
                        <TableRow key={k}>
                          <TableCell className="align-top font-mono text-xs">
                            {k}
                          </TableCell>
                          <TableCell className="max-w-[min(100vw,28rem)] break-all font-mono text-xs whitespace-pre-wrap">
                            {formatChannelFieldValue(v)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </TabsContent>
            <TabsContent
              value="raw"
              className="mt-3 min-h-0 flex-1 overflow-hidden"
            >
              <div className="max-h-[min(60vh,560px)] overflow-y-auto overscroll-contain rounded-md border">
                <pre className="p-3 font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-all">
                  {JSON.stringify(payload, null, 2)}
                </pre>
              </div>
            </TabsContent>
          </Tabs>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}

export function NewApiPage() {
  const qc = useQueryClient()
  const cfgQ = useQuery({
    queryKey: ["newapi-config"],
    queryFn: () => apiFetch<NewApiConfig>("/api/newapi/config"),
  })
  const chQ = useQuery({
    queryKey: ["newapi-channels"],
    queryFn: () => apiFetch<ChannelRow[]>("/api/newapi/channels"),
  })

  const [form, setForm] = useState({
    base_url: "",
    admin_token: "",
    admin_user_id: "",
    min_coupon_balance_for_newapi: 10,
    template_json: DEFAULT_NEWAPI_TEMPLATE_JSON,
  })

  useEffect(() => {
    if (!cfgQ.data) return
    const c = cfgQ.data
    const tmpl = c.template
    setForm({
      base_url: c.base_url,
      admin_token: c.admin_token,
      admin_user_id: c.admin_user_id,
      min_coupon_balance_for_newapi:
        typeof c.min_coupon_balance_for_newapi === "number" &&
        !Number.isNaN(c.min_coupon_balance_for_newapi)
          ? c.min_coupon_balance_for_newapi
          : 10,
      template_json: JSON.stringify(
        tmpl && typeof tmpl === "object" && !Array.isArray(tmpl) && Object.keys(tmpl).length > 0
          ? tmpl
          : JSON.parse(DEFAULT_NEWAPI_TEMPLATE_JSON) as Record<string, unknown>,
        null,
        2,
      ),
    })
  }, [cfgQ.data])

  const saveMut = useMutation({
    mutationFn: () => {
      let template: Record<string, unknown>
      try {
        const parsed = JSON.parse(form.template_json.trim() || "{}")
        if (
          parsed === null ||
          typeof parsed !== "object" ||
          Array.isArray(parsed)
        ) {
          throw new Error("Template must be a JSON object")
        }
        const ch = parsed.channel
        if (
          ch === null ||
          typeof ch !== "object" ||
          Array.isArray(ch)
        ) {
          throw new Error('Template must include a "channel" object (new-api channel data)')
        }
        template = parsed as Record<string, unknown>
      } catch (e) {
        const msg =
          e instanceof Error ? e.message : "Invalid JSON in template"
        throw new Error(msg)
      }
      const mb = Number(form.min_coupon_balance_for_newapi)
      const minBal =
        Number.isFinite(mb) && mb >= 0 ? mb : 10
      return apiFetch<NewApiConfig>("/api/newapi/config", {
        method: "PUT",
        body: JSON.stringify({
          base_url: form.base_url,
          admin_token: form.admin_token,
          admin_user_id: form.admin_user_id,
          min_coupon_balance_for_newapi: minBal,
          template,
        }),
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["newapi-config"] })
      qc.invalidateQueries({ queryKey: ["newapi-channels"] })
      toast.success("Configuration saved")
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const syncMut = useMutation({
    mutationFn: () =>
      apiFetch<{ ok: boolean }>("/api/newapi/sync", { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["newapi-channels"] })
      toast.success("Channels synced")
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const [inspectChannelId, setInspectChannelId] = useState<number | null>(null)
  const [manualChannelId, setManualChannelId] = useState("")

  if (cfgQ.error) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Unauthorized or error</AlertTitle>
        <AlertDescription>{(cfgQ.error as Error).message}</AlertDescription>
      </Alert>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">new-api</h1>

      <Tabs defaultValue="channels">
        <TabsList>
          <TabsTrigger value="channels">Channels</TabsTrigger>
          <TabsTrigger value="config">Configuration</TabsTrigger>
        </TabsList>

        <TabsContent value="channels" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Channels</CardTitle>
              <CardDescription>
                Channels linked to Alibaba Cloud accounts (priorities 1000, 1001, … from coupon
                expiry and min balance — see Configuration). Use Sync on the Configuration tab to
                push updates to new-api.
              </CardDescription>
              <div className="flex flex-wrap items-end gap-2 pt-2">
                <div className="grid gap-1">
                  <Label className="text-xs">Query by channel ID</Label>
                  <Input
                    className="h-8 w-36 font-mono text-sm"
                    inputMode="numeric"
                    placeholder="e.g. 123"
                    value={manualChannelId}
                    onChange={(e) => setManualChannelId(e.target.value)}
                  />
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  className="shrink-0"
                  onClick={() => {
                    const n = Number.parseInt(manualChannelId.trim(), 10)
                    if (Number.isNaN(n) || n <= 0) {
                      toast.error("Enter a positive channel ID")
                      return
                    }
                    setInspectChannelId(n)
                  }}
                >
                  Fetch detail
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="shrink-0"
                  onClick={() => qc.invalidateQueries({ queryKey: ["newapi-channels"] })}
                >
                  <RefreshCw className="mr-2 h-4 w-4" />
                  Refresh list
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {chQ.isLoading ? (
                <Loader2 className="h-6 w-6 animate-spin" />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>ID</TableHead>
                      <TableHead>Name</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Priority</TableHead>
                      <TableHead>Aliyun</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(chQ.data ?? []).length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="text-muted-foreground">
                          No linked channels. Add Aliyun accounts and configure new-api, or use
                          &quot;Query by channel ID&quot; above.
                        </TableCell>
                      </TableRow>
                    ) : (
                      (chQ.data ?? []).map((row) => (
                        <TableRow key={row.id}>
                          <TableCell>{row.id}</TableCell>
                          <TableCell>{row.name}</TableCell>
                          <TableCell>{statusLabel(row.status)}</TableCell>
                          <TableCell>{row.priority ?? "—"}</TableCell>
                          <TableCell className="font-mono text-xs">
                            {row.aliyun_account_id ?? "—"}
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              size="icon"
                              variant="ghost"
                              title="View channel detail (raw)"
                              onClick={() => setInspectChannelId(row.id)}
                            >
                              <Eye className="h-4 w-4" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="config" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Admin API</CardTitle>
              <CardDescription>
                new-api administrator access token and user id (New-Api-User header). Save, then
                sync channels to apply template and eligibility rules on the remote.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4">
              {cfgQ.isLoading ? (
                <Loader2 className="h-6 w-6 animate-spin" />
              ) : (
                <>
                  <div className="grid gap-2">
                    <Label>Base URL</Label>
                    <Input
                      value={form.base_url}
                      onChange={(e) =>
                        setForm({ ...form, base_url: e.target.value })
                      }
                      placeholder="https://new-api.example.com"
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label>Admin access token</Label>
                    <Input
                      type="password"
                      value={form.admin_token}
                      onChange={(e) =>
                        setForm({ ...form, admin_token: e.target.value })
                      }
                      placeholder="Paste token to replace masked value"
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label>Admin user id</Label>
                    <Input
                      value={form.admin_user_id}
                      onChange={(e) =>
                        setForm({ ...form, admin_user_id: e.target.value })
                      }
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label>Min coupon balance for sync</Label>
                    <Input
                      type="number"
                      min={0}
                      step="any"
                      className="max-w-xs font-mono text-sm"
                      value={form.min_coupon_balance_for_newapi}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          min_coupon_balance_for_newapi:
                            Number.parseFloat(e.target.value) || 0,
                        })
                      }
                    />
                    <p className="text-muted-foreground text-xs">
                      Aliyun cash coupon balance must be <strong>strictly greater</strong> than this
                      value (same unit as BSS) for the account to get a new-api channel. Others are
                      removed on sync.
                    </p>
                  </div>
                  <Separator />
                  <div className="grid gap-2">
                    <Label>Channel template (JSON)</Label>
                    <Textarea
                      className="min-h-[min(50vh,420px)] font-mono text-xs"
                      value={form.template_json}
                      onChange={(e) =>
                        setForm({ ...form, template_json: e.target.value })
                      }
                      spellCheck={false}
                    />
                    <p className="text-muted-foreground text-xs">
                      Single object: <code className="text-xs">name_template</code> (placeholders{" "}
                      <code className="text-xs">{"{username}"}</code>,{" "}
                      <code className="text-xs">{"{id}"}</code>) and{" "}
                      <code className="text-xs">channel</code> — the new-api channel{" "}
                      <code className="text-xs">data</code> object (no <code className="text-xs">id</code>
                      ). Sync overwrites <code className="text-xs">name</code>,{" "}
                      <code className="text-xs">priority</code>, <code className="text-xs">key</code>,{" "}
                      <code className="text-xs">remark</code> only. Priority is sequential{" "}
                      <code className="text-xs">1000</code>, <code className="text-xs">1001</code>, … by
                      coupon expiry (soonest first, among coupons above min balance), then account
                      age if no qualifying coupons.
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      onClick={() => saveMut.mutate()}
                      disabled={saveMut.isPending}
                    >
                      Save
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => syncMut.mutate()}
                      disabled={syncMut.isPending}
                    >
                      <RefreshCw className="mr-2 h-4 w-4" />
                      Sync channels
                    </Button>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <ChannelInspectorDialog
        channelId={inspectChannelId}
        open={inspectChannelId !== null}
        onOpenChange={(v) => {
          if (!v) setInspectChannelId(null)
        }}
      />
    </div>
  )
}
