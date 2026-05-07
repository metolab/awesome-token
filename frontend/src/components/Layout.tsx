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
import { Menu, X } from "lucide-react"

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
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchAuthSession().then((s) => {
      if (!cancelled) setSession(s)
    })
    return () => {
      cancelled = true
    }
  }, [])

  // Close sidebar on route change (mobile)
  useEffect(() => {
    setSidebarOpen(false)
  }, [loc.pathname])

  const sidebarContent = (
    <>
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
    </>
  )

  return (
    <div className="flex h-screen w-full overflow-hidden">
      {/* Desktop sidebar */}
      <aside className="hidden md:flex w-56 flex-col border-r border-border bg-sidebar p-3">
        {sidebarContent}
      </aside>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 md:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden
        />
      )}

      {/* Mobile sidebar drawer */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-56 flex-col border-r border-border bg-sidebar p-3 transition-transform duration-200 md:hidden",
          sidebarOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <Button
          size="icon"
          variant="ghost"
          className="absolute top-2 right-2 h-7 w-7"
          onClick={() => setSidebarOpen(false)}
          aria-label="Close menu"
        >
          <X className="h-4 w-4" />
        </Button>
        {sidebarContent}
      </aside>

      <div className="flex flex-1 flex-col min-w-0 overflow-hidden">
        {/* Mobile top bar */}
        <div className="flex items-center gap-2 border-b border-border px-4 py-2 md:hidden">
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open menu"
          >
            <Menu className="h-5 w-5" />
          </Button>
          <span className="text-sm font-semibold tracking-tight">awesome-token</span>
        </div>

        <main className="flex-1 overflow-auto p-4 sm:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
