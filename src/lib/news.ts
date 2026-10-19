import base from "@/data/news.json";

export interface NewsItem {
  id: string;
  title: string;
  summary: string;
  content: string;
  source: string;
  date: string;
  category: string;
  imageUrl?: string;
}

export const news: NewsItem[] = (base as NewsItem[]).slice().sort((a, b) => b.date.localeCompare(a.date));

export const categories = Array.from(new Set(news.map((n) => n.category)));

export function filterNews(items: NewsItem[], query: string, category: string | null) {
  const q = query.trim().toLowerCase();
  return items.filter(
    (n) =>
      (!category || n.category === category) &&
      (!q || n.title.toLowerCase().includes(q) || n.category.toLowerCase().includes(q)),
  );
}

export function formatDate(d: string) {
  return new Date(d + "T12:00:00").toLocaleDateString("es-AR", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}
