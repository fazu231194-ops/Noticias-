import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { Masthead } from "@/components/Masthead";
import { categories, filterNews, formatDate, news } from "@/lib/news";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Panorama Global News — Portal de noticias" },
      { name: "description", content: "Las últimas noticias de tecnología, economía, deportes y más." },
      { property: "og:title", content: "Panorama Global News — Portal de noticias" },
      { property: "og:description", content: "Las últimas noticias de tecnología, economía, deportes y más." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

function Index() {
  const [query, setQuery] = useState("");
  const [cat, setCat] = useState<string | null>(null);
  const list = filterNews(news, query, cat);
  const [lead, ...rest] = list;

  return (
    <div className="min-h-screen">
      <Masthead />
      <nav className="sticky top-0 z-10 border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto max-w-6xl px-4 py-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex gap-2 overflow-x-auto">
            {[null, ...categories].map((c) => (
              <button
                key={c ?? "all"}
                onClick={() => setCat(c)}
                className={`shrink-0 px-3 py-1 text-xs font-semibold uppercase tracking-wider border transition-colors ${
                  cat === c ? "bg-primary text-primary-foreground border-primary" : "border-border hover:border-foreground"
                }`}
              >
                {c ?? "Todas"}
              </button>
            ))}
          </div>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar por título o categoría…"
            className="w-full md:w-72 border border-input bg-card px-3 py-2 text-sm outline-none focus:border-foreground"
          />
        </div>
      </nav>

      <main className="mx-auto max-w-6xl px-4 py-8">
        {!lead ? (
          <p className="py-20 text-center text-muted-foreground">No se encontraron noticias.</p>
        ) : (
          <>
            <Link
              to="/noticia/$id"
              params={{ id: lead.id }}
              className="group grid gap-6 md:grid-cols-5 border-b border-border pb-8"
            >
              {lead.imageUrl && (
                <img src={lead.imageUrl} alt={lead.title} className="md:col-span-3 aspect-[16/10] w-full object-cover" />
              )}
              <div className="md:col-span-2 flex flex-col justify-center">
                <span className="text-xs font-bold uppercase tracking-widest text-primary">{lead.category}</span>
                <h2 className="mt-2 font-display text-3xl sm:text-4xl font-bold leading-tight group-hover:underline">
                  {lead.title}
                </h2>
                <p className="mt-3 text-muted-foreground">{lead.summary}</p>
                <p className="mt-4 text-xs text-muted-foreground">
                  {lead.source} · {formatDate(lead.date)}
                </p>
              </div>
            </Link>
            <div className="mt-8 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
              {rest.map((n) => (
                <Link key={n.id} to="/noticia/$id" params={{ id: n.id }} className="group block">
                  {n.imageUrl && <img src={n.imageUrl} alt={n.title} loading="lazy" className="aspect-[16/10] w-full object-cover" />}
                  <span className="mt-3 block text-xs font-bold uppercase tracking-widest text-primary">{n.category}</span>
                  <h3 className="mt-1 font-display text-xl font-bold leading-snug group-hover:underline">{n.title}</h3>
                  <p className="mt-2 text-sm text-muted-foreground line-clamp-3">{n.summary}</p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {n.source} · {formatDate(n.date)}
                  </p>
                </Link>
              ))}
            </div>
          </>
        )}
      </main>
      <footer className="border-t border-border py-6 text-center text-xs text-muted-foreground">
        © 2026 Panorama Global News
      </footer>
    </div>
  );
}
