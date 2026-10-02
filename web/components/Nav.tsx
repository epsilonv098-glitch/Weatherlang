"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Activity, BarChart3, Map as MapIcon, Moon, Sun, Waves } from "lucide-react";

const TABS = [
  { href: "/", label: "Map", Icon: MapIcon },
  { href: "/beaches", label: "Beaches", Icon: Waves },
  { href: "/compare", label: "Compare", Icon: BarChart3 },
  { href: "/pipeline", label: "Pipeline", Icon: Activity },
];

export default function Nav() {
  const path = usePathname();
  const [light, setLight] = useState(false);

  useEffect(() => {
    try {
      if (localStorage.getItem("theme") === "light") {
        document.documentElement.dataset.theme = "light";
        setLight(true);
      }
    } catch {}
  }, []);

  function toggleTheme() {
    const next = !light;
    setLight(next);
    document.documentElement.dataset.theme = next ? "light" : "dark";
    try {
      localStorage.setItem("theme", next ? "light" : "dark");
    } catch {}
  }

  const active = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));

  return (
    <>
      <header className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 pt-5">
        <div>
          <Link href="/" className="text-xl font-semibold tracking-tight">Cebu Pulse</Link>
          <p className="text-sm text-[var(--muted)]">Live data for the Queen City of the South</p>
        </div>
        <nav aria-label="Main" className="hidden gap-1 sm:flex">
          {TABS.map(({ href, label }) => (
            <Link key={href} href={href} aria-current={active(href) ? "page" : undefined}
              className={`rounded-xl px-3 py-2 text-sm transition-colors hover:bg-[var(--card)] ${active(href) ? "bg-[var(--card)] font-medium" : "text-[var(--muted)]"}`}>
              {label}
            </Link>
          ))}
        </nav>
        <button onClick={toggleTheme} aria-label={light ? "Switch to dark mode" : "Switch to light mode"}
          className="rounded-xl border border-[var(--border)] p-2 transition-colors hover:bg-[var(--card)]">
          {light ? <Moon size={18} /> : <Sun size={18} />}
        </button>
      </header>

      <nav aria-label="Main" className="glass fixed inset-x-0 bottom-0 z-[1100] flex justify-around rounded-b-none rounded-t-2xl pb-[env(safe-area-inset-bottom)] sm:hidden">
        {TABS.map(({ href, label, Icon }) => (
          <Link key={href} href={href} aria-current={active(href) ? "page" : undefined}
            className={`flex flex-1 flex-col items-center gap-1 py-3 text-xs ${active(href) ? "font-semibold text-[var(--accent)]" : "text-[var(--muted)]"}`}>
            <Icon size={20} aria-hidden />
            {label}
          </Link>
        ))}
      </nav>
    </>
  );
}
