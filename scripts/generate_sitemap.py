import json
import os
from xml.sax.saxutils import escape

SITE_URL = "https://noticiasnoticiasglobales.pages.dev"
NEWS_FILE = "src/data/news.json"
OUT_FILE = "public/sitemap.xml"


def main():
    with open(NEWS_FILE, "r", encoding="utf-8") as archivo:
        noticias = json.load(archivo)

    noticias = [n for n in noticias if isinstance(n, dict) and n.get("id")]
    fechas = [n.get("publishedAt", "") for n in noticias if n.get("publishedAt")]
    ultima = max(fechas) if fechas else None

    lineas = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]

    portada = f"  <url><loc>{SITE_URL}/</loc>"
    if ultima:
        portada += f"<lastmod>{escape(ultima)}</lastmod>"
    portada += "<changefreq>hourly</changefreq><priority>1.0</priority></url>"
    lineas.append(portada)

    for n in noticias:
        url = f"{SITE_URL}/noticia/{n['id']}"
        item = f"  <url><loc>{escape(url)}</loc>"
        if n.get("publishedAt"):
            item += f"<lastmod>{escape(n['publishedAt'])}</lastmod>"
        item += "</url>"
        lineas.append(item)

    lineas.append("</urlset>")

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as archivo:
        archivo.write("\n".join(lineas) + "\n")

    print(f"Sitemap generado con {len(noticias) + 1} URLs.")


if __name__ == "__main__":
    main()
