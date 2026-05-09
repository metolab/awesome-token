import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Eye, Loader2, Plus, RefreshCw, X } from "lucide-react"
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

const DEFAULT_NEWAPI_TEMPLATES_JSON = `[
  {
    "name_template": "Aliyun {username}",
    "channel": {}
  }
]`

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

function cloneJsonObject<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function sortUniqueModelNames(values: Iterable<string>): string[] {
  const deduped = new Map<string, string>()
  for (const raw of values) {
    const value = raw.trim()
    if (!value) continue
    const key = value.toLocaleLowerCase()
    if (!deduped.has(key)) deduped.set(key, value)
  }
  return Array.from(deduped.values()).sort((a, b) =>
    a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" }),
  )
}

function parseModelNames(value: unknown): string[] {
  if (Array.isArray(value)) {
    return sortUniqueModelNames(value.map((item) => String(item)))
  }
  if (typeof value !== "string") return []
  return sortUniqueModelNames(value.split(","))
}

function parseFreeformModelInput(value: string): string[] {
  return sortUniqueModelNames(value.split(/[,\n]+/))
}

/**
 * Extract the shared models list from the first template entry that has channel.models,
 * and return a cleaned templates array with models removed from every entry's channel.
 * This mirrors the old splitTemplateModels() but operates on an array.
 */
function splitModelsFromTemplates(templates: Record<string, unknown>[]): {
  models: string[]
  hadModelsField: boolean
  templates: Record<string, unknown>[]
} {
  let models: string[] = []
  let hadModelsField = false
  const cleaned = templates.map((entry) => {
    const e = cloneJsonObject(entry)
    const ch =
      e.channel && typeof e.channel === "object" && !Array.isArray(e.channel)
        ? (e.channel as Record<string, unknown>)
        : null
    if (ch && "models" in ch) {
      hadModelsField = true
      if (models.length === 0) {
        models = parseModelNames(ch.models)
      }
      const newCh = { ...ch }
      delete newCh.models
      return { ...e, channel: newCh }
    }
    return e
  })
  return { models, hadModelsField, templates: cleaned }
}

/**
 * Inject the shared models string into every template entry's channel.models.
 */
function injectModelsIntoTemplates(
  templates: Record<string, unknown>[],
  channelModels: string[],
): Record<string, unknown>[] {
  const modelsStr = sortUniqueModelNames(channelModels).join(",")
  return templates.map((entry) => {
    const e = cloneJsonObject(entry)
    const ch =
      e.channel && typeof e.channel === "object" && !Array.isArray(e.channel)
        ? { ...(e.channel as Record<string, unknown>) }
        : {}
    ch.models = modelsStr
    return { ...e, channel: ch }
  })
}

/** Normalise the server value for `template` into a JSON array string for the textarea. */
function normalisedTemplatesWithoutModels(raw: unknown): {
  json: string
  models: string[]
} {
  let arr: Record<string, unknown>[]
  if (Array.isArray(raw) && raw.length > 0) {
    arr = raw as Record<string, unknown>[]
  } else if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    arr = [raw as Record<string, unknown>]
  } else {
    return { json: DEFAULT_NEWAPI_TEMPLATES_JSON, models: [] }
  }
  const { models, templates } = splitModelsFromTemplates(arr)
  return { json: JSON.stringify(templates, null, 2), models }
}

function ChannelModelsInput({
  inputValue,
  onAddInputValue,
  onInputValueChange,
  onRemoveModel,
  selectedModels,
}: {
  inputValue: string
  onAddInputValue: () => void
  onInputValueChange: (value: string) => void
  onRemoveModel: (model: string) => void
  selectedModels: string[]
}) {
  return (
    <div className="grid gap-3">
      <div className="flex items-center justify-between gap-2">
        <Label>Channel models (shared across all template entries)</Label>
        <span className="text-muted-foreground text-xs">
          {selectedModels.length} selected
        </span>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          value={inputValue}
          onChange={(e) => onInputValueChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault()
              onAddInputValue()
            }
          }}
          placeholder="Type model names, then press Enter or comma"
          spellCheck={false}
        />
        <Button
          type="button"
          variant="secondary"
          className="sm:self-start"
          onClick={onAddInputValue}
          disabled={!inputValue.trim()}
        >
          <Plus className="mr-2 h-4 w-4" />
          Add
        </Button>
      </div>
      <div className="rounded-md border p-3">
        {selectedModels.length === 0 ? (
          <p className="text-muted-foreground text-xs">
            No models selected yet.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {selectedModels.map((model) => (
              <Badge
                key={model}
                variant="secondary"
                className="h-auto gap-1 px-2 py-1 font-mono text-[11px]"
              >
                {model}
                <button
                  type="button"
                  className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full hover:bg-black/10"
                  onClick={() => onRemoveModel(model)}
                  aria-label={`Remove ${model}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            ))}
          </div>
        )}
      </div>
      <p className="text-muted-foreground text-xs">
        Injected as <code className="text-xs">channel.models</code> into every template entry on
        save. Stored as a sorted comma-separated string.
      </p>
    </div>
  )
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
    max_channels_for_newapi_sync: 5,
    templates_json: DEFAULT_NEWAPI_TEMPLATES_JSON,
  })
  const [channelModels, setChannelModels] = useState<string[]>([])
  const [modelInput, setModelInput] = useState("")

  useEffect(() => {
    if (!cfgQ.data) return
    const c = cfgQ.data
    const { json, models } = normalisedTemplatesWithoutModels(c.template)
    setChannelModels(models)
    setModelInput("")
    setForm({
      base_url: c.base_url,
      admin_token: c.admin_token,
      admin_user_id: c.admin_user_id,
      min_coupon_balance_for_newapi:
        typeof c.min_coupon_balance_for_newapi === "number" &&
        !Number.isNaN(c.min_coupon_balance_for_newapi)
          ? c.min_coupon_balance_for_newapi
          : 10,
      max_channels_for_newapi_sync:
        typeof c.max_channels_for_newapi_sync === "number" &&
        Number.isInteger(c.max_channels_for_newapi_sync) &&
        c.max_channels_for_newapi_sync >= 1
          ? c.max_channels_for_newapi_sync
          : 5,
      templates_json: json,
    })
  }, [cfgQ.data])

  function addModels(rawValue: string) {
    const nextModels = parseFreeformModelInput(rawValue)
    if (nextModels.length === 0) return
    setChannelModels((prev) => sortUniqueModelNames([...prev, ...nextModels]))
  }

  function commitModelInput() {
    if (!modelInput.trim()) return
    addModels(modelInput)
    setModelInput("")
  }

  function removeSelectedModel(model: string) {
    setChannelModels((prev) => prev.filter((item) => item !== model))
  }

  function handleTemplatesJsonChange(value: string) {
    let nextValue = value
    try {
      const parsed: unknown = JSON.parse(value.trim() || "[]")
      if (Array.isArray(parsed) && parsed.length > 0) {
        const { hadModelsField, models, templates } = splitModelsFromTemplates(
          parsed as Record<string, unknown>[],
        )
        if (hadModelsField) {
          setChannelModels(models)
          nextValue = JSON.stringify(templates, null, 2)
        }
      }
    } catch {
      // Keep the raw textarea content while the user edits invalid JSON.
    }
    setForm((prev) => ({ ...prev, templates_json: nextValue }))
  }

  const saveMut = useMutation({
    mutationFn: () => {
      let baseTemplates: Record<string, unknown>[]
      try {
        const raw = form.templates_json.trim() || "[]"
        const parsed: unknown = JSON.parse(raw)
        if (!Array.isArray(parsed)) {
          throw new Error("Templates must be a JSON array")
        }
        for (let i = 0; i < parsed.length; i++) {
          const entry = parsed[i]
          if (entry === null || typeof entry !== "object" || Array.isArray(entry)) {
            throw new Error(`templates[${i}] must be an object`)
          }
          const ch = (entry as Record<string, unknown>).channel
          if (ch === null || typeof ch !== "object" || Array.isArray(ch)) {
            throw new Error(
              `templates[${i}].channel must be an object (new-api channel data)`,
            )
          }
        }
        baseTemplates = parsed as Record<string, unknown>[]
      } catch (e) {
        throw new Error(e instanceof Error ? e.message : "Invalid JSON in templates")
      }
      const template = injectModelsIntoTemplates(baseTemplates, channelModels)
      const mb = Number(form.min_coupon_balance_for_newapi)
      const minBal = Number.isFinite(mb) && mb >= 0 ? mb : 10
      const maxCh = Math.max(1, Math.round(Number(form.max_channels_for_newapi_sync)) || 5)
      return apiFetch<NewApiConfig>("/api/newapi/config", {
        method: "PUT",
        body: JSON.stringify({
          base_url: form.base_url,
          admin_token: form.admin_token,
          admin_user_id: form.admin_user_id,
          min_coupon_balance_for_newapi: minBal,
          max_channels_for_newapi_sync: maxCh,
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
      <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">new-api</h1>

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
                Channels linked to Alibaba Cloud accounts. Each eligible account gets one channel
                per template entry (Template #). Priorities 1000, 1001, … by coupon expiry — see
                Configuration.
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
                      <TableHead>Template #</TableHead>
                      <TableHead>Aliyun</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(chQ.data ?? []).length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} className="text-muted-foreground">
                          No linked channels. Add Aliyun accounts and configure new-api, or use
                          &quot;Query by channel ID&quot; above.
                        </TableCell>
                      </TableRow>
                    ) : (
                      (chQ.data ?? []).map((row) => (
                        <TableRow key={`${row.id}-${row.template_index ?? "x"}`}>
                          <TableCell>{row.id}</TableCell>
                          <TableCell>{row.name}</TableCell>
                          <TableCell>{statusLabel(row.status)}</TableCell>
                          <TableCell>{row.priority ?? "—"}</TableCell>
                          <TableCell className="font-mono text-xs">
                            {row.template_index != null ? row.template_index : "—"}
                          </TableCell>
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
                      value (same unit as BSS) for the account to get new-api channels. Others are
                      removed on sync.
                    </p>
                  </div>
                  <div className="grid gap-2">
                    <Label>Max accounts to sync</Label>
                    <Input
                      type="number"
                      min={1}
                      step={1}
                      className="max-w-xs font-mono text-sm"
                      value={form.max_channels_for_newapi_sync}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          max_channels_for_newapi_sync:
                            Math.max(1, Math.round(Number.parseInt(e.target.value, 10) || 5)),
                        })
                      }
                    />
                    <p className="text-muted-foreground text-xs">
                      Only the top-N highest-priority eligible accounts (by soonest coupon expiry)
                      receive new-api channels. Accounts ranked beyond this limit have their
                      channels removed on sync. Default: <strong>5</strong>.
                    </p>
                  </div>
                  <Separator />
                  <ChannelModelsInput
                    inputValue={modelInput}
                    onAddInputValue={commitModelInput}
                    onInputValueChange={setModelInput}
                    onRemoveModel={removeSelectedModel}
                    selectedModels={channelModels}
                  />
                  <div className="grid gap-2">
                    <Label>Channel templates (JSON array)</Label>
                    <Textarea
                      className="min-h-[min(50vh,420px)] font-mono text-xs"
                      value={form.templates_json}
                      onChange={(e) => handleTemplatesJsonChange(e.target.value)}
                      spellCheck={false}
                    />
                    <p className="text-muted-foreground text-xs">
                      JSON array of template entries. Each entry has{" "}
                      <code className="text-xs">name_template</code> (placeholders{" "}
                      <code className="text-xs">{"{username}"}</code>,{" "}
                      <code className="text-xs">{"{id}"}</code>) and{" "}
                      <code className="text-xs">channel</code> — the new-api channel{" "}
                      <code className="text-xs">data</code> object (omit{" "}
                      <code className="text-xs">id</code> and{" "}
                      <code className="text-xs">models</code> — managed by the selector above).
                      Each eligible account receives one channel per array entry. Sync overwrites{" "}
                      <code className="text-xs">name</code>,{" "}
                      <code className="text-xs">priority</code>,{" "}
                      <code className="text-xs">key</code>,{" "}
                      <code className="text-xs">remark</code>, and{" "}
                      <code className="text-xs">models</code> only.
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
