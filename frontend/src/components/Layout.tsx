import { useEffect, useState } from "react"
import { Link, Outlet, useLocation } from "react-router-dom"
import {
  fetchAuthSession,
  redirectToLogin,
  type AuthSession,
} from "@/api/client"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"

const nav = [
  { to: "/", label: "Aliyun accounts" },
  { to: "/new-api", label: "new-api" },
  { to: "/scheduler", label: "Scheduler" },
  { to: "/logs", label: "Logs" },
]

export function Layout() {
  const loc = useLocation()
  const [session, setSession] = useState<AuthSession | null | undefined>(
    undefined,
  )

  useEffect(() => {
    let cancelled = false
    fetchAuthSession().then((s) => {
      if (!cancelled) setSession(s)
    })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="flex min-h-screen w-full">
      <aside className="flex w-56 flex-col border-r border-border bg-sidebar p-3">
        <div className="mb-3 text-sm font-semibold tracking-tight">
          awesome-token
        </div>
        <nav className="flex flex-col gap-0.5">
          {nav.map((item) => (
            <Link key={item.to} to={item.to}>
              <Button
                size="sm"
                variant={loc.pathname === item.to ? "secondary" : "ghost"}
                className={cn("h-7 w-full justify-start text-xs")}
              >
                {item.label}
              </Button>
            </Link>
          ))}
        </nav>
        <Separator className="my-3" />
        {session === undefined ? (
          <div className="text-muted-foreground text-xs">Loading…</div>
        ) : session ? (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2 rounded-md border border-border bg-background/50 px-1.5 py-1">
              {session.avatar_url ? (
                <img
                  src={session.avatar_url}
                  alt=""
                  className="size-7 shrink-0 rounded-full bg-muted"
                  width={28}
                  height={28}
                />
              ) : (
                <div
                  className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-medium text-muted-foreground"
                  aria-hidden
                >
                  {(session.email?.split("@")[0] ?? "?").slice(0, 2).toUpperCase()}
                </div>
              )}
              {session.email ? (
                <div
                  className="min-w-0 flex-1 truncate text-xs leading-tight text-foreground"
                  title={session.email}
                >
                  {session.email}
                </div>
              ) : null}
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-full text-xs"
              onClick={async () => {
                await fetch("/auth/logout", {
                  method: "POST",
                  credentials: "include",
                })
                window.location.reload()
              }}
            >
              Sign out
            </Button>
          </div>
        ) : (
          <Button
            variant="outline"
            size="sm"
            className="h-7 w-full text-xs"
            type="button"
            onClick={() => redirectToLogin()}
          >
            Sign in
          </Button>
        )}
      </aside>
      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>
    </div>
  )
}
