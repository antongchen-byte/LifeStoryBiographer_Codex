"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import {
  BookOpen,
  LayoutGrid,
  Sparkles,
  Mic,
  Clapperboard,
  Film,
  LogOut,
  ArrowUpRight,
} from "lucide-react";
import { useEffect, type ReactNode } from "react";
const routes = [
  { href: "/", label: "My biographies", icon: LayoutGrid },
  { href: "/style-lab", label: "Style Lab", icon: Sparkles, number: "01" },
  {
    href: "/interview-studio",
    label: "Interview Studio",
    icon: Mic,
    number: "02",
  },
  {
    href: "/screenplay-editor",
    label: "Screenplay Editor",
    icon: Clapperboard,
    number: "03",
  },
  { href: "/cinema-studio", label: "Cinema Studio", icon: Film, number: "04" },
];
export default function AppShell({ children }: { children: ReactNode }) {
  const path = usePathname(),
    router = useRouter();
  const { data: session, status } = useSession();
  useEffect(() => {
    if (status === "unauthenticated" && path !== "/login")
      router.replace("/login");
  }, [status, path, router]);
  if (path === "/login") return children;
  if (status !== "authenticated")
    return <div className="loading-screen">Opening your studio…</div>;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/" className="brand">
          <span className="brand-icon">
            <BookOpen size={22} />
          </span>
          <span>
            LifeStory<span className="brand-subtitle">BIOGRAPHER</span>
          </span>
        </Link>
        <div className="workspace-label">YOUR WORKSPACE</div>
        <nav aria-label="Main navigation">
          {routes.filter(route => process.env.NEXT_PUBLIC_ENABLE_FILM_STUDIOS !== "false" || !["/screenplay-editor", "/cinema-studio"].includes(route.href)).map(({ href, label, icon: Icon, number }) => (
            <Link
              key={href}
              href={href}
              className={`nav-link ${path === href || (href !== "/" && path.startsWith(`${href}/`)) || (href === "/" && path.startsWith("/projects")) ? "active" : ""}`}
            >
              <Icon size={18} />
              <span>{label}</span>
              {number && <small>{number}</small>}
            </Link>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="tiny-label">A LIFE, WELL TOLD</span>
          <p>
            Every photograph.
            <br />
            Every memory.
            <br />A story worth keeping.
          </p>
          <BookOpen size={25} />
        </div>
        <div className="profile">
          <span className="avatar">{session.user?.name?.slice(0, 1)}</span>
          <div>
            <strong>{session.user?.name}</strong>
            <small>Personal workspace</small>
          </div>
          <button
            className="icon-button"
            aria-label="Sign out"
            onClick={() => void signOut({ callbackUrl: "/login" })}
          >
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      <div className="main-column" data-background={path.startsWith("/interview-studio") ? "conversation" : path.startsWith("/style-lab") ? "garden" : "memories"}>
        <header className="topbar">
          <span>YOUR STORY STARTS HERE</span>
          <a href="/" className="topbar-link">
            Biography workspace <ArrowUpRight size={14} />
          </a>
        </header>
        <main>{children}</main>
        <footer>Made from memories. Shaped by you.</footer>
      </div>
    </div>
  );
}
