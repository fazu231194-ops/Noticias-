import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { AdBanner } from "@/components/Ads";
import { Masthead } from "@/components/Masthead";
import { formatDate, news } from "@/lib/news";

export const Route = createFileRoute("/noticia/$id")({
  loader: ({ params }) => {
    const item = news.find((n) => n.id === params.id);
    if (!item) throw notFound();
    return item;
  },
  head: ({ loaderData }) => {
    if (!loaderData) return { meta: [{ title: "Noticia no encontrada" }, { name: "robots", content: "noindex" }] };
    const meta = [
      { title: `${loaderData.title} — Panorama Global News` },
      { name: "description", content: loaderData.summary },
      { property: "og:title", content: loaderData.title },
      { property: "og:description", content: loaderData.summary },
      { property: "og:type", content: "article" },
      { name: "twitter:card", content: "summary_large_image" },
    ];
    if (loaderData.imageUrl)
      meta.push(
        { property: "og:image", content: loaderData.imageUrl },
        { name: "twitter:image", content: loaderData.imageUrl },
      );
    return { meta };
  },
  notFoundComponent: () => (
    <div className="min-h-screen">
      <Masthead />
      <p className="py-20 text-center">
        Noticia no encontrada. <Link to="/" className="underline">Volver a portada</Link>
      </p>
    </div>
  ),
  component: Detail,
});

function Detail() {
  const n = Route.useLoaderData();
  const related = news.filter((x) => x.id !== n.id).slice(0, 3);
  return (
    <div className="min-h-screen">
      <Masthead />
      <article className="mx-auto max-w-3xl px-4 py-8">
        <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">← Volver a portada</Link>
        <span className="mt-6 block text-xs font-bold uppercase tracking-widest text-primary">{n.category}</span>
        <h1 className="mt-2 font-display text-3xl sm:text-5xl font-black leading-tight">{n.title}</h1>
        <p className="mt-4 text-lg italic text-muted-foreground">{n.summary}</p>
        <p className="mt-4 border-y border-border py-2 text-xs uppercase tracking-wider text-muted-foreground">
          Por {n.source} · {formatDate(n.date)}
        </p>
        {n.imageUrl && <img src={n.imageUrl} alt={n.title} className="mt-6 w-full aspect-[16/9] object-cover" />}
        <div className="mt-6 text-lg leading-relaxed first-letter:float-left first-letter:mr-2 first-letter:font-display first-letter:text-6xl first-letter:font-black first-letter:leading-none">
          {n.content}
        </div>
        <AdBanner />
      </article>
      <section className="mx-auto max-w-3xl px-4 pb-12">
        <h2 className="border-b-2 border-foreground pb-1 font-display text-xl font-bold">Más noticias</h2>
        <ul className="mt-4 divide-y divide-border">
          {related.map((r) => (
            <li key={r.id} className="py-3">
              <Link to="/noticia/$id" params={{ id: r.id }} className="font-semibold hover:underline">{r.title}</Link>
              <p className="text-xs text-muted-foreground">{r.category} · {formatDate(r.date)}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
