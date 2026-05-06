import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import type { ColumnDef } from "@tanstack/react-table"
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table"
import { Copy, Loader2, Pencil, RefreshCw, Trash2 } from "lucide-react"
import { useCallback, useMemo, useState } from "react"
import { toast } from "sonner"
import {
  type AliyunAccount,
  type AliyunAccountDetail,
  type BillLineRow,
  type CashCouponSnapshot,
  type NewApiConfig,
  type OpenApiKeyCreatedResponse,
  type OpenApiKeyListItem,
  type QueryBillLiveResponse,
  apiFetch,
} from "@/api/client"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
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
import { copyTextToClipboard } from "@/lib/utils"

function parseMoney(s: string | null | undefined): number {
  if (s == null || s === "") return 0
  const n = Number.parseFloat(String(s).replace(/,/g, ""))
  return Number.isFinite(n) ? n : 0
}

function parseTimestamp(iso: string | null | undefined): number | null {
  if (!iso) return null
  const t = new Date(iso).getTime()
  return Number.isNaN(t) ? null : t
}

function compareNullableTimestampsAsc(
  a: string | null | undefined,
  b: string | null | undefined,
): number {
  const ta = parseTimestamp(a)
  const tb = parseTimestamp(b)
  if (ta == null && tb == null) return 0
  if (ta == null) return 1
  if (tb == null) return -1
  return ta - tb
}

function sortCouponsByExpiry(
  coupons: CashCouponSnapshot[] | undefined,
): CashCouponSnapshot[] {
  if (!coupons?.length) return []
  return [...coupons].sort((a, b) => {
    const byExpiry = compareNullableTimestampsAsc(a.expiry_time, b.expiry_time)
    if (byExpiry !== 0) return byExpiry
    const byGranted = compareNullableTimestampsAsc(a.granted_time, b.granted_time)
    if (byGranted !== 0) return byGranted
    return String(a.coupon_id ?? "").localeCompare(String(b.coupon_id ?? ""), undefined, {
      sensitivity: "base",
    })
  })
}

function firstCouponExpiry(coupons: CashCouponSnapshot[] | undefined): string | null {
  for (const coupon of coupons ?? []) {
    if (parseTimestamp(coupon.expiry_time) != null) {
      return coupon.expiry_time ?? null
    }
  }
  return null
}

function sortAccountsByCouponExpiry(accounts: AliyunAccount[] | undefined): AliyunAccount[] {
  if (!accounts?.length) return []
  const normalized = accounts.map((account) => ({
    ...account,
    coupons: sortCouponsByExpiry(account.coupons),
  }))
  return normalized.sort((a, b) => {
    const byExpiry = compareNullableTimestampsAsc(
      firstCouponExpiry(a.coupons),
      firstCouponExpiry(b.coupons),
    )
    if (byExpiry !== 0) return byExpiry
    const byCreatedAt = compareNullableTimestampsAsc(a.created_at, b.created_at)
    if (byCreatedAt !== 0) return byCreatedAt
    return a.username.localeCompare(b.username, undefined, { sensitivity: "base" })
  })
}

function couponIsExpired(coupon: CashCouponSnapshot): boolean {
  return (coupon.status ?? "").trim().toLowerCase() === "expired"
}

function couponQualifiesForSync(
  coupon: CashCouponSnapshot,
  minBalance: number,
): boolean {
  if (couponIsExpired(coupon)) return false
  return parseMoney(coupon.balance) > minBalance
}

function accountQualifiesForSync(
  account: AliyunAccount,
  minBalance: number,
): boolean {
  return account.coupons.some((coupon) => couponQualifiesForSync(coupon, minBalance))
}

/** Sum of remaining balance (free) and sum of nominal face value (total) across all coupons. */
function sumCouponFreeAndTotal(coupons: CashCouponSnapshot[] | undefined): {
  free: number
  total: number
} | null {
  if (!coupons?.length) return null
  let total = 0
  let free = 0
  for (const c of coupons) {
    const nominal = parseMoney(c.nominal_value)
    const balance = parseMoney(c.balance)
    total += nominal
    free += balance
  }
  return { free, total }
}

function formatExpiry(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  })
}

const BILLING_PAGE_SIZE = 50

function defaultBillingCycle(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`
}

function billingMonthOptions(count = 24): string[] {
  const out: string[] = []
  const now = new Date()
  for (let i = 0; i < count; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    out.push(
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`,
    )
  }
  return out
}

function fmtCny(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—"
  return new Intl.NumberFormat(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  }).format(n)
}

function fmtText(s: string | null | undefined): string {
  if (s == null) return "—"
  const t = String(s).trim()
  return t.length > 0 ? t : "—"
}

function billStatusBadgeVariant(
  s: string | null | undefined,
): "default" | "secondary" | "destructive" | "outline" {
  if (!s) return "outline"
  if (s === "PayFinish") return "default"
  if (s.includes("Unsettle") || s.includes("Unclear")) return "secondary"
  if (s.includes("Cancel") || s.includes("Fail")) return "destructive"
  return "outline"
}

function BillLineCard({ line }: { line: BillLineRow }) {
  const codes = [line.product_code, line.commodity_code, line.pip_code].filter(
    Boolean,
  ) as string[]
  const codeLine = codes.length ? codes.join(" · ") : null

  return (
    <div className="bg-card rounded-lg border p-4 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="text-foreground text-base font-semibold leading-snug">
            {fmtText(line.product_name)}
          </div>
          {line.product_detail ? (
            <p className="text-muted-foreground text-sm leading-relaxed">
              {line.product_detail}
            </p>
          ) : null}
          {codeLine ? (
            <p className="text-muted-foreground font-mono text-xs tracking-tight">
              {codeLine}
              {line.product_type ? (
                <span className="text-muted-foreground/80">
                  {" "}
                  ({line.product_type})
                </span>
              ) : null}
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {line.item ? (
            <Badge variant="outline" className="font-mono text-xs">
              {line.item}
            </Badge>
          ) : null}
          {line.subscription_type ? (
            <Badge variant="secondary" className="text-xs">
              {line.subscription_type}
            </Badge>
          ) : null}
          {line.status ? (
            <Badge variant={billStatusBadgeVariant(line.status)} className="text-xs">
              {line.status}
            </Badge>
          ) : null}
        </div>
      </div>

      <Separator className="my-4" />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-0.5">
          <div className="text-muted-foreground text-xs">Pretax gross</div>
          <div className="font-mono text-sm tabular-nums">
            {fmtCny(line.pretax_gross_amount)} {line.currency ?? ""}
          </div>
        </div>
        <div className="space-y-0.5">
          <div className="text-muted-foreground text-xs">Pretax</div>
          <div className="font-mono text-sm tabular-nums">{fmtCny(line.pretax_amount)}</div>
        </div>
        <div className="space-y-0.5">
          <div className="text-muted-foreground text-xs">After tax</div>
          <div className="font-mono text-sm tabular-nums">{fmtCny(line.after_tax_amount)}</div>
        </div>
        <div className="space-y-0.5">
          <div className="text-muted-foreground text-xs">Tax</div>
          <div className="font-mono text-sm tabular-nums">{fmtCny(line.tax)}</div>
        </div>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <div className="space-y-0.5">
          <div className="text-muted-foreground text-xs">Deducted · cash coupon</div>
          <div className="font-mono text-sm text-emerald-700 tabular-nums dark:text-emerald-400">
            {fmtCny(line.deducted_by_cash_coupons)}
          </div>
        </div>
        <div className="space-y-0.5">
          <div className="text-muted-foreground text-xs">Deducted · coupon</div>
          <div className="font-mono text-sm text-emerald-700 tabular-nums dark:text-emerald-400">
            {fmtCny(line.deducted_by_coupons)}
          </div>
        </div>
        <div className="space-y-0.5">
          <div className="text-muted-foreground text-xs">Cash paid</div>
          <div className="font-mono text-sm tabular-nums">{fmtCny(line.cash_amount)}</div>
        </div>
      </div>

      <Separator className="my-4" />

      <div className="text-muted-foreground space-y-2 text-xs leading-relaxed">
        <div>
          <span className="font-medium text-foreground">Usage</span>{" "}
          <span className="font-mono">
            {fmtText(line.usage_start_time)} → {fmtText(line.usage_end_time)}
          </span>
        </div>
        <div>
          <span className="font-medium text-foreground">Payment time</span>{" "}
          <span className="font-mono">{fmtText(line.payment_time)}</span>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono">
          <span>
            <span className="text-foreground font-sans font-medium">Record</span>{" "}
            {fmtText(line.record_id)}
          </span>
        </div>
      </div>
    </div>
  )
}

function AccountBillsDialog({
  account,
  onOpenChange,
}: {
  account: AliyunAccount
  onOpenChange: (v: boolean) => void
}) {
  const [billingCycle, setBillingCycle] = useState(defaultBillingCycle)
  const [page, setPage] = useState(1)
  const id = account.id

  const billQ = useQuery({
    queryKey: ["bss-query-bill", id, billingCycle, page],
    queryFn: () => {
      const q = new URLSearchParams({
        billing_cycle: billingCycle,
        page: String(page),
        page_size: String(BILLING_PAGE_SIZE),
      })
      return apiFetch<QueryBillLiveResponse>(
        `/api/aliyun/accounts/${id}/bills?${q}`,
      )
    },
    enabled: !!id,
    staleTime: 0,
  })

  const total = billQ.data?.total_count ?? 0
  const totalPages = Math.max(1, Math.ceil(total / BILLING_PAGE_SIZE))

  const pageTotals = useMemo(() => {
    const items = billQ.data?.items ?? []
    let pretaxGross = 0
    let deductedCoupon = 0
    let deductedCashCoupon = 0
    for (const x of items) {
      pretaxGross += x.pretax_gross_amount ?? 0
      deductedCoupon += x.deducted_by_coupons ?? 0
      deductedCashCoupon += x.deducted_by_cash_coupons ?? 0
    }
    return { pretaxGross, deductedCoupon, deductedCashCoupon, n: items.length }
  }, [billQ.data?.items])

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] max-w-6xl flex-col gap-0 overflow-hidden p-0 sm:max-w-6xl">
        <DialogHeader className="shrink-0 border-b px-4 py-3 sm:px-6 sm:py-4">
          <DialogTitle>Billing — {account.username}</DialogTitle>
          <p className="text-muted-foreground text-sm font-normal">
            Alibaba Cloud BSS <code className="text-xs">QueryBill</code>（按自然月出账）·
            仅实时查询，不落库
          </p>
        </DialogHeader>

        <div className="flex shrink-0 flex-wrap items-end gap-3 border-b px-4 py-2 sm:px-6 sm:py-3">
          <div className="grid gap-1.5">
            <Label htmlFor="billing-cycle">Billing month</Label>
            <select
              id="billing-cycle"
              className="border-input bg-background ring-offset-background focus-visible:ring-ring flex h-9 min-w-[9rem] rounded-md border px-3 py-1 text-sm shadow-sm focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
              value={billingCycle}
              onChange={(e) => {
                setBillingCycle(e.target.value)
                setPage(1)
              }}
            >
              {billingMonthOptions(24).map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={!id || billQ.isFetching}
            onClick={() => billQ.refetch()}
          >
            {billQ.isFetching ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            Refresh
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 sm:px-6 sm:py-4">
          {billQ.error && (
            <div className="text-destructive mb-3 text-sm">
              {(billQ.error as Error).message}
            </div>
          )}

          {billQ.isLoading && id ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : billQ.data ? (
            <div className="space-y-4">
              <div className="bg-muted/40 flex flex-wrap items-baseline gap-x-5 gap-y-2 rounded-lg border px-4 py-3 text-sm">
                <div>
                  <span className="text-muted-foreground">账期 </span>
                  <span className="text-foreground font-semibold tabular-nums">
                    {billQ.data.billing_cycle}
                  </span>
                </div>
                {billQ.data.bss_account_id ? (
                  <div>
                    <span className="text-muted-foreground">BSS ID </span>
                    <span className="font-mono text-xs">{billQ.data.bss_account_id}</span>
                  </div>
                ) : null}
                {billQ.data.bss_account_name ? (
                  <div>
                    <span className="text-muted-foreground">账户名 </span>
                    <span className="text-foreground font-medium">
                      {billQ.data.bss_account_name}
                    </span>
                  </div>
                ) : null}
                <div>
                  <span className="text-muted-foreground">本页 </span>
                  <span className="text-foreground font-medium">{pageTotals.n}</span>
                  <span className="text-muted-foreground"> 条</span>
                  {total > 0 ? (
                    <span className="text-muted-foreground">
                      {" "}
                      （共 {total} 条）
                    </span>
                  ) : null}
                </div>
                {billQ.data.bss_code != null || billQ.data.bss_message != null ? (
                  <div className="text-muted-foreground w-full text-xs sm:w-auto">
                    {billQ.data.bss_code ? `${billQ.data.bss_code}` : ""}
                    {billQ.data.bss_message ? ` · ${billQ.data.bss_message}` : ""}
                  </div>
                ) : null}
                {billQ.data.request_id ? (
                  <div className="w-full font-mono text-[11px] text-muted-foreground sm:w-auto">
                    RequestId {billQ.data.request_id}
                  </div>
                ) : null}
              </div>

              {pageTotals.n > 1 && (
                <div className="text-muted-foreground flex flex-wrap gap-x-6 gap-y-1 border-b pb-3 text-xs">
                  <span>
                    本页税前原价合计{" "}
                    <span className="text-foreground font-mono font-medium">
                      {fmtCny(pageTotals.pretaxGross)}
                    </span>
                  </span>
                  <span>
                    代金券抵扣合计{" "}
                    <span className="font-mono font-medium text-emerald-700 dark:text-emerald-400">
                      {fmtCny(pageTotals.deductedCoupon)}
                    </span>
                  </span>
                  <span>
                    现金券抵扣合计{" "}
                    <span className="font-mono font-medium text-emerald-700 dark:text-emerald-400">
                      {fmtCny(pageTotals.deductedCashCoupon)}
                    </span>
                  </span>
                </div>
              )}

              {billQ.data.items.length === 0 && billQ.data.bss_success === true && (
                <p className="rounded-md border border-dashed bg-muted/40 px-3 py-2 text-sm">
                  本月 QueryBill 无明细行（尚无计费或账单未出齐，可切换其它月份）。
                </p>
              )}
              {billQ.data.items.length === 0 &&
                billQ.data.bss_success !== true &&
                (billQ.data.bss_code != null || billQ.data.bss_message != null) && (
                  <p className="rounded-md border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-sm">
                    BSS: {billQ.data.bss_code ?? "?"}{" "}
                    {billQ.data.bss_message ?? ""}
                  </p>
                )}

              <div className="flex flex-col gap-4">
                {billQ.data.items.map((row, i) => (
                  <BillLineCard key={`${row.record_id ?? "row"}-${i}`} line={row} />
                ))}
              </div>

              {total > BILLING_PAGE_SIZE && (
                <div className="flex items-center justify-between gap-4">
                  <p className="text-muted-foreground text-sm">
                    Page {page} of {totalPages}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={page <= 1 || billQ.isFetching}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                    >
                      Previous
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={page >= totalPages || billQ.isFetching}
                      onClick={() => setPage((p) => p + 1)}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              )}
            </div>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function OpenApiKeysPanel() {
  const qc = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ["openapi-keys"],
    queryFn: () => apiFetch<OpenApiKeyListItem[]>("/api/openapi/keys"),
  })
  const [label, setLabel] = useState("")
  const [secretDialog, setSecretDialog] =
    useState<OpenApiKeyCreatedResponse | null>(null)
  const [revokeRow, setRevokeRow] = useState<OpenApiKeyListItem | null>(null)

  const createMut = useMutation({
    mutationFn: () =>
      apiFetch<OpenApiKeyCreatedResponse>("/api/openapi/keys", {
        method: "POST",
        body: JSON.stringify({ label: label.trim() }),
      }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["openapi-keys"] })
      setSecretDialog(res)
      setLabel("")
      toast.success("Key created — copy it now; it will not be shown again.")
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const delMut = useMutation({
    mutationFn: (id: string) =>
      apiFetch<{ ok: boolean }>(`/api/openapi/keys/${encodeURIComponent(id)}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["openapi-keys"] })
      toast.success("Key revoked")
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const endpointUrl =
    typeof window !== "undefined"
      ? `${window.location.origin}/openapi/v1/bailian-token`
      : "/openapi/v1/bailian-token"

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>OpenAPI</CardTitle>
          <CardDescription>
            API keys authenticate requests that return the Bailian API key for the account that
            currently has the highest new-api channel priority (same coupon threshold and ordering
            as on the new-api page). Send{" "}
            <code className="text-xs">Authorization: Bearer &lt;key&gt;</code> or{" "}
            <code className="text-xs">X-Api-Key</code>.
          </CardDescription>
          <div className="flex flex-wrap items-end gap-2 pt-2">
            <div className="grid gap-1">
              <Label className="text-xs" htmlFor="openapi-label">
                Label (optional)
              </Label>
              <Input
                id="openapi-label"
                className="h-8 max-w-xs text-sm"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="e.g. prod script"
              />
            </div>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="shrink-0"
              disabled={createMut.isPending}
              onClick={() => createMut.mutate()}
            >
              Generate key
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="bg-muted/40 rounded-md border px-3 py-2 font-mono text-xs break-all">
            GET {endpointUrl}
          </div>
          {isLoading ? (
            <Loader2 className="h-6 w-6 animate-spin" />
          ) : error ? (
            <p className="text-destructive text-sm">{(error as Error).message}</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Key</TableHead>
                  <TableHead>Label</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {!data?.length ? (
                  <TableRow>
                    <TableCell colSpan={4} className="text-muted-foreground">
                      No keys yet
                    </TableCell>
                  </TableRow>
                ) : (
                  data.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell className="font-mono text-xs">
                        {row.key_plain ? (
                          <div className="flex items-center gap-1.5">
                            <span className="truncate max-w-[16rem]" title={row.key_plain}>
                              {row.key_plain}
                            </span>
                            <Button
                              type="button"
                              size="icon"
                              variant="ghost"
                              className="h-6 w-6 shrink-0"
                              title="Copy key"
                              onClick={async (e) => {
                                e.stopPropagation()
                                const ok = await copyTextToClipboard(row.key_plain!)
                                if (ok) toast.success("Copied to clipboard")
                                else toast.error("Copy failed")
                              }}
                            >
                              <Copy className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        ) : (
                          row.key_prefix
                        )}
                      </TableCell>
                      <TableCell>{row.label || "—"}</TableCell>
                      <TableCell className="text-muted-foreground text-xs">
                        {new Date(row.created_at).toLocaleString()}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="icon"
                          variant="ghost"
                          title="Revoke"
                          disabled={delMut.isPending}
                          onClick={() => setRevokeRow(row)}
                        >
                          <Trash2 className="text-destructive h-4 w-4" />
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

      <Dialog open={!!secretDialog} onOpenChange={() => setSecretDialog(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Copy your API key</DialogTitle>
          </DialogHeader>
          <p className="text-muted-foreground text-sm">
            This secret is shown only once. Store it in a password manager or secret store.
          </p>
          {secretDialog ? (
            <div className="space-y-2">
              <Label htmlFor="openapi-secret-once">Secret</Label>
              <Input
                id="openapi-secret-once"
                readOnly
                className="font-mono text-xs"
                value={secretDialog.secret}
                onFocus={(e) => e.target.select()}
              />
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={async () => {
                  const ok = await copyTextToClipboard(secretDialog.secret)
                  if (ok) toast.success("Copied to clipboard")
                  else
                    toast.error(
                      "Copy failed — focus the field above and copy manually (Ctrl/Cmd+C).",
                    )
                }}
              >
                Copy to clipboard
              </Button>
            </div>
          ) : null}
          <DialogFooter>
            <Button type="button" onClick={() => setSecretDialog(null)}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={!!revokeRow}
        onOpenChange={(open) => {
          if (!open) setRevokeRow(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke API key?</AlertDialogTitle>
            <AlertDialogDescription>
              {revokeRow
                ? `Key ${revokeRow.key_prefix} will stop working for any client that still uses it. This cannot be undone.`
                : null}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (revokeRow) delMut.mutate(revokeRow.id)
                setRevokeRow(null)
              }}
            >
              Revoke
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

export function AliyunAccountsPage() {
  const qc = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ["aliyun-accounts"],
    queryFn: () => apiFetch<AliyunAccount[]>("/api/aliyun/accounts/"),
  })
  const cfgQ = useQuery({
    queryKey: ["newapi-config"],
    queryFn: () => apiFetch<NewApiConfig>("/api/newapi/config"),
  })
  const accounts = useMemo(() => sortAccountsByCouponExpiry(data), [data])
  const minCouponBalanceForSync =
    typeof cfgQ.data?.min_coupon_balance_for_newapi === "number" &&
    Number.isFinite(cfgQ.data.min_coupon_balance_for_newapi) &&
    cfgQ.data.min_coupon_balance_for_newapi >= 0
      ? cfgQ.data.min_coupon_balance_for_newapi
      : 10

  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<AliyunAccount | null>(null)
  const [form, setForm] = useState({
    username: "",
    access_key_id: "",
    access_key_secret: "",
    bailian_api_key: "",
    remark: "",
  })
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const [billingAccount, setBillingAccount] = useState<AliyunAccount | null>(null)
  const [editLoadingId, setEditLoadingId] = useState<string | null>(null)
  const [hideBelowMinCouponBalance, setHideBelowMinCouponBalance] = useState(true)

  const hiddenAccountCount = useMemo(
    () =>
      accounts.filter(
        (account) => !accountQualifiesForSync(account, minCouponBalanceForSync),
      ).length,
    [accounts, minCouponBalanceForSync],
  )

  const visibleAccounts = useMemo(
    () =>
      hideBelowMinCouponBalance
        ? accounts.filter((account) =>
            accountQualifiesForSync(account, minCouponBalanceForSync),
          )
        : accounts,
    [accounts, hideBelowMinCouponBalance, minCouponBalanceForSync],
  )

  const resetForm = () => {
    setForm({
      username: "",
      access_key_id: "",
      access_key_secret: "",
      bailian_api_key: "",
      remark: "",
    })
    setEditing(null)
  }

  const createMut = useMutation({
    mutationFn: () =>
      apiFetch<AliyunAccount>("/api/aliyun/accounts/", {
        method: "POST",
        body: JSON.stringify(form),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["aliyun-accounts"] })
      toast.success("Account saved")
      setOpen(false)
      resetForm()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const updateMut = useMutation({
    mutationFn: () => {
      const body: Record<string, string> = {
        username: form.username,
        remark: form.remark,
      }
      if (form.access_key_id) body.access_key_id = form.access_key_id
      if (form.access_key_secret) body.access_key_secret = form.access_key_secret
      if (form.bailian_api_key) body.bailian_api_key = form.bailian_api_key
      return apiFetch<AliyunAccount>(`/api/aliyun/accounts/${editing!.id}`, {
        method: "PUT",
        body: JSON.stringify(body),
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["aliyun-accounts"] })
      toast.success("Updated")
      setOpen(false)
      resetForm()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) =>
      apiFetch<{ ok: boolean }>(`/api/aliyun/accounts/${id}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["aliyun-accounts"] })
      toast.success("Deleted")
      setDeleteId(null)
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const openEditDialog = useCallback(async (account: AliyunAccount) => {
    setEditLoadingId(account.id)
    try {
      const detail = await apiFetch<AliyunAccountDetail>(
        `/api/aliyun/accounts/${account.id}`,
      )
      setEditing(detail)
      setForm({
        username: detail.username,
        access_key_id: detail.access_key_id,
        access_key_secret: detail.access_key_secret,
        bailian_api_key: detail.bailian_api_key,
        remark: detail.remark,
      })
      setOpen(true)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setEditLoadingId(null)
    }
  }, [])

  const syncMut = useMutation({
    mutationFn: (id: string) =>
      apiFetch<AliyunAccount>(`/api/aliyun/accounts/${id}/sync`, {
        method: "POST",
      }),
    onSuccess: () => {
      toast.success("Synced from Alibaba Cloud")
    },
    onError: (e: Error) => toast.error(e.message),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["aliyun-accounts"] })
    },
  })

  const columns = useMemo<ColumnDef<AliyunAccount>[]>(
    () => [
      { accessorKey: "username", header: "Username" },
      { accessorKey: "remark", header: "Remark" },
      {
        id: "balance",
        header: "Balance",
        cell: ({ row }) => {
          const b = row.original.balance
          if (!b?.available_amount && !b?.available_cash_amount) return "—"
          return `${b.available_cash_amount ?? b.available_amount ?? "—"} ${b.currency ?? ""}`
        },
      },
      {
        id: "coupons",
        header: "Coupons",
        cell: ({ row }) => {
          const coupons = row.original.coupons
          const n = coupons?.length ?? 0
          if (!n) return "—"
          const sums = sumCouponFreeAndTotal(coupons)
          const firstExpiry = firstCouponExpiry(coupons)
          return (
            <div className="flex flex-col gap-0.5 text-sm leading-tight">
              <span>
                {sums
                  ? `${sums.free.toFixed(2)} / ${sums.total.toFixed(2)} CNY`
                  : "—"}
                <span className="text-muted-foreground ml-1.5 text-xs">
                  ({n} {n === 1 ? "coupon" : "coupons"})
                </span>
              </span>
              <span className="text-muted-foreground text-xs">
                1st expires: {formatExpiry(firstExpiry)}
              </span>
            </div>
          )
        },
      },
      {
        id: "sync_status",
        header: "Sync",
        cell: ({ row }) => {
          const err = row.original.last_sync_error
          if (err) {
            return (
              <span
                className="text-destructive max-w-[min(18rem,28vw)] truncate text-xs"
                title={err}
              >
                {err}
              </span>
            )
          }
          if (row.original.last_synced_at) {
            return <Badge variant="secondary">OK</Badge>
          }
          return <span className="text-muted-foreground text-xs">—</span>
        },
      },
      {
        id: "channel",
        header: "new-api ch.",
        cell: ({ row }) =>
          row.original.newapi_channel_id ? (
            <Badge variant="outline">{row.original.newapi_channel_id}</Badge>
          ) : (
            "—"
          ),
      },
      {
        id: "created_at",
        header: "Added",
        cell: ({ row }) => (
          <span className="text-muted-foreground text-xs">
            {new Date(row.original.created_at).toLocaleDateString()}
          </span>
        ),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
            <Button
              size="icon"
              variant="ghost"
              onClick={() => syncMut.mutate(row.original.id)}
              title="Sync BSS"
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              disabled={editLoadingId === row.original.id}
              onClick={() => void openEditDialog(row.original)}
            >
              {editLoadingId === row.original.id ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Pencil className="h-4 w-4" />
              )}
            </Button>
            <Button
              size="icon"
              variant="ghost"
              onClick={() => setDeleteId(row.original.id)}
            >
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          </div>
        ),
      },
    ],
    [editLoadingId, openEditDialog, syncMut],
  )

  const table = useReactTable({
    data: visibleAccounts,
    columns,
    getCoreRowModel: getCoreRowModel(),
  })

  if (error) {
    return (
      <div className="text-destructive">
        Failed to load (are you signed in?) — {(error as Error).message}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">
        Alibaba Cloud accounts
      </h1>

      <Tabs defaultValue="accounts">
        <TabsList>
          <TabsTrigger value="accounts">Accounts</TabsTrigger>
          <TabsTrigger value="openapi">OpenAPI</TabsTrigger>
        </TabsList>

        <TabsContent value="accounts" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Accounts</CardTitle>
              <CardDescription>
                Click a row to open bill lines for that account (BSS QueryBill).
              </CardDescription>
              <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
                <label className="text-muted-foreground flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-primary"
                    checked={hideBelowMinCouponBalance}
                    onChange={(e) => setHideBelowMinCouponBalance(e.target.checked)}
                  />
                  <span>
                    Hide below Min coupon balance for sync (
                    {hideBelowMinCouponBalance ? hiddenAccountCount : 0})
                  </span>
                </label>
                <Button
                  type="button"
                  onClick={() => {
                    resetForm()
                    setOpen(true)
                  }}
                >
                  Add account
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <Loader2 className="h-6 w-6 animate-spin" />
              ) : (
                <Table>
                  <TableHeader>
                    {table.getHeaderGroups().map((hg) => (
                      <TableRow key={hg.id}>
                        {hg.headers.map((h) => (
                          <TableHead key={h.id}>
                            {flexRender(
                              h.column.columnDef.header,
                              h.getContext(),
                            )}
                          </TableHead>
                        ))}
                      </TableRow>
                    ))}
                  </TableHeader>
                  <TableBody>
                    {table.getRowModel().rows.length === 0 ? (
                      <TableRow>
                        <TableCell
                          colSpan={columns.length}
                          className="text-muted-foreground"
                        >
                          {accounts.length === 0
                            ? "No accounts yet"
                            : "All accounts are hidden by the min sync balance filter. Clear the checkbox to show all accounts."}
                        </TableCell>
                      </TableRow>
                    ) : (
                      table.getRowModel().rows.map((row) => (
                        <TableRow
                          key={row.id}
                          className="hover:bg-muted/50 cursor-pointer"
                          onClick={(e) => {
                            if ((e.target as HTMLElement).closest("button"))
                              return
                            setBillingAccount(row.original)
                          }}
                        >
                          {row.getVisibleCells().map((cell) => (
                            <TableCell key={cell.id}>
                              {flexRender(
                                cell.column.columnDef.cell,
                                cell.getContext(),
                              )}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="openapi" className="space-y-4">
          <OpenApiKeysPanel />
        </TabsContent>
      </Tabs>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editing ? "Edit account" : "Add account"}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div className="grid gap-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="ak">AccessKey ID</Label>
              <Input
                id="ak"
                value={form.access_key_id}
                onChange={(e) => setForm({ ...form, access_key_id: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="sk">AccessKey secret</Label>
              <Input
                id="sk"
                value={form.access_key_secret}
                onChange={(e) =>
                  setForm({ ...form, access_key_secret: e.target.value })
                }
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="bk">Bailian API key</Label>
              <Input
                id="bk"
                value={form.bailian_api_key}
                onChange={(e) =>
                  setForm({ ...form, bailian_api_key: e.target.value })
                }
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="rm">Remark</Label>
              <Input
                id="rm"
                value={form.remark}
                onChange={(e) => setForm({ ...form, remark: e.target.value })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() =>
                editing ? updateMut.mutate() : createMut.mutate()
              }
              disabled={createMut.isPending || updateMut.isPending}
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {billingAccount ? (
        <AccountBillsDialog
          key={billingAccount.id}
          account={billingAccount}
          onOpenChange={(v) => {
            if (!v) setBillingAccount(null)
          }}
        />
      ) : null}

      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete account?</AlertDialogTitle>
            <AlertDialogDescription>
              This removes the record and attempts to delete the linked new-api channel.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteId && deleteMut.mutate(deleteId)}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
