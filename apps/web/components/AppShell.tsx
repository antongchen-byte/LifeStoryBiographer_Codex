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
import WorkingContext from "./WorkingContext";
import ProductionShare from "./ProductionShare";
import ProductionContext from "./ProductionContext";
import {request} from "../lib/api";
import {useQuery} from "@tanstack/react-query";
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
  const capability=useQuery({queryKey:["production-capability",session?.user?.email],queryFn:()=>request<{production_editor:boolean;actor_id:string}>("/production/me"),enabled:status==="authenticated"});
  useEffect(() => {
    if (status === "unauthenticated" && path !== "/login")
      router.replace("/login");
  }, [status, path, router]);
  if (path === "/login") return children;
  if (status !== "authenticated")
    return <div className="loading-screen">Opening your studio…</div>;
  if (capability.isPending) return <div className="loading-screen">Opening your studio…</div>;
  if (capability.isError) return <div className="loading-screen">Unable to verify workspace access. Reload to retry; your selected project has been kept.</div>;
  if (typeof window !== "undefined") {
    const working=sessionStorage.getItem("working-project");
    if(working && JSON.parse(working).actor_id !== capability.data?.actor_id)sessionStorage.removeItem("working-project");
    const stored=sessionStorage.getItem("production-project");
    if(stored && (!capability.data?.production_editor || JSON.parse(stored).actor_id !== capability.data?.actor_id)) sessionStorage.removeItem("production-project");
  }
  const filmAllowed = process.env.NEXT_PUBLIC_ENABLE_FILM_STUDIOS !== "false" &&
    (process.env.NEXT_PUBLIC_FILM_STUDIOS_EDITOR_ONLY !== "true" || capability.data?.production_editor === true);
  const filmPage = path.startsWith("/screenplay-editor") || path.startsWith("/cinema-studio");
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
          {capability.data?.production_editor && <Link className="nav-link" href="/production-projects">Production projects</Link>}
          {routes.filter(route => filmAllowed || !["/screenplay-editor", "/cinema-studio"].includes(route.href)).map(({ href, label, icon: Icon, number }) => (
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
            onClick={() => {sessionStorage.removeItem("production-project");sessionStorage.removeItem("working-project");void signOut({ callbackUrl: "/login" });}}
          >
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      <div className="main-column" data-background={path.startsWith("/screenplay-editor") ? "screenplay" : path.startsWith("/cinema-studio") ? "cinema" : path.startsWith("/interview-studio") ? "conversation" : path.startsWith("/style-lab") ? "garden" : "memories"}>
        <header className="topbar">
          <span>YOUR STORY STARTS HERE</span>
          <a href="/" className="topbar-link">
            Biography workspace <ArrowUpRight size={14} />
          </a>
        </header>
        <main><WorkingContext />{capability.data?.production_editor && <ProductionContext />}<div id="module-page-content">{filmPage && !filmAllowed ? <p role="alert">This studio is available to Production Editors. Your shared editor materials are available from My biographies.</p> : children}</div>{capability.data?.production_editor && <ProductionShare />}</main>
        <footer>Made from memories. Shaped by you.</footer>
      </div>
    </div>
  );
}
