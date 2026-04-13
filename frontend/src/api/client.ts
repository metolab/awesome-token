/**
 * All API calls use same-origin relative URLs (/api, /auth) so the Vite dev proxy
 * forwards to the backend. Do not use VITE_API_BASE_URL pointing at 127.0.0.1 — browsers
 * block public-origin pages from fetching loopback (Private Network Access).
 */
function apiUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path
  }
  return path.startsWith("/") ? path : `/${path}`
}

/** Redirect browser to OAuth login; preserves return path after sign-in. */
export function redirectToLogin(): void {
  const next = window.location.pathname + window.location.search
  const qs = next && next !== "/" ? `?next=${encodeURIComponent(next)}` : ""
  window.location.replace(`/auth/login${qs}`)
}

export type AuthSession = {
  sub: string
  email: string | null
  username: string
  avatar_url: string | null
}

export type OpenApiKeyListItem = {
  id: string
  label: string
  key_prefix: string
  created_at: string
}

export type OpenApiKeyCreatedResponse = {
  id: string
  label: string
  key_prefix: string
  secret: string
  created_at: string
}

/** Current session from cookie, or null if not signed in (does not redirect). */
export async function fetchAuthSession(): Promise<AuthSession | null> {
  const res = await fetch(apiUrl("/auth/me"), { credentials: "include" })
  if (res.status === 401) {
    return null
  }
  if (!res.ok) {
    return null
  }
  return res.json() as Promise<AuthSession>
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const url = apiUrl(path)
  let res: Response
  try {
    res = await fetch(url, {
      ...init,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    })
  } catch {
    throw new Error(
      "Failed to fetch — ensure the dev server proxies /api to the backend (same-origin only, no loopback URL in the browser).",
    )
  }

  if (res.status === 401) {
    if (!path.startsWith("/auth/")) {
      redirectToLogin()
      await new Promise<never>(() => {})
    }
    throw new Error("Unauthorized")
  }
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  if (res.status === 204) {
    return undefined as T
  }
  return res.json() as Promise<T>
}

export type BalanceSnapshot = {
  available_amount?: string | null
  available_cash_amount?: string | null
  currency?: string | null
}

export type CashCouponSnapshot = {
  coupon_id?: string | null
  status?: string | null
  balance?: string | null
  nominal_value?: string | null
  granted_time?: string | null
  expiry_time?: string | null
}

export type AliyunAccount = {
  id: string
  username: string
  remark: string
  balance: BalanceSnapshot | null
  coupons: CashCouponSnapshot[]
  last_synced_at: string | null
  /** Set when the last BSS sync failed; cleared on success. */
  last_sync_error?: string | null
  newapi_channel_id: number | null
  created_at: string
  updated_at: string
}

export type AliyunAccountDetail = AliyunAccount & {
  access_key_id: string
  last_transactions: Record<string, unknown>[]
}

export type BillLineRow = {
  product_name?: string | null
  product_code?: string | null
  product_type?: string | null
  product_detail?: string | null
  subscription_type?: string | null
  item?: string | null
  pretax_gross_amount?: number | null
  pretax_amount?: number | null
  after_tax_amount?: number | null
  currency?: string | null
  deducted_by_cash_coupons?: number | null
  deducted_by_coupons?: number | null
  cash_amount?: number | null
  payment_time?: string | null
  usage_start_time?: string | null
  usage_end_time?: string | null
  status?: string | null
  record_id?: string | null
  tax?: number | null
  pip_code?: string | null
  commodity_code?: string | null
}

export type QueryBillLiveResponse = {
  account_id: string
  username: string
  billing_cycle: string
  page_num?: number | null
  page_size?: number | null
  total_count?: number | null
  bss_account_id?: string | null
  bss_account_name?: string | null
  items: BillLineRow[]
  bss_success?: boolean | null
  bss_code?: string | null
  bss_message?: string | null
  request_id?: string | null
}

/** Admin URL + token + single JSON template: { name_template, channel }. */
export type NewApiConfig = {
  id: string
  base_url: string
  admin_token: string
  admin_user_id: string
  template: Record<string, unknown>
  /** Coupon balance must be strictly above this (BSS currency) to sync a channel. */
  min_coupon_balance_for_newapi: number
}

export type ScheduledJob = {
  id: string
  name: string
  interval_minutes: number
  enabled: boolean
}

export type JobRunLogEntry = {
  job_id: string
  at: string
  ok: boolean
  message: string
  duration_ms: number
}

export type AppLogEntry = {
  ts: string
  level: string
  logger: string
  message: string
}

export type ChannelRow = {
  id: number
  name?: string | null
  type?: number | null
  status?: number | null
  priority?: number | null
  models?: string | null
  group?: string | null
  aliyun_account_id?: string | null
}

/** Full JSON from new-api GET /api/channel/{id} (wrapped by backend). */
export type ChannelDetailResponse = {
  channel_id: number
  body: Record<string, unknown>
}
