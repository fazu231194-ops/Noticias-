
import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import feedparser

NEWS_FILE_PATH = "src/data/news.json"
MAX_NOTICIAS = 300
POR_FUENTE = 10
IMAGEN_POR_DEFECTO = "https://images.unsplash.com/photo-1504711434969-e33886168f5c?auto=format&fit=crop&w=800&q=80"
RSS_FEEDS = [
    # Argentina: medios nacionales
    ("https://www.lanacion.com.ar/arc/outboundfeeds/rss/?outputType=xml", "Sociedad"),
    ("https://www.clarin.com/rss/lo-ultimo/", "Sociedad"),
    ("https://www.infobae.com/feeds/rss/", "Mundo"),
    ("https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/tecnologia", "Tecnología"),
    # Estados Unidos: medios y agencias con feeds disponibles
    ("https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "Mundo"),
    ("https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "Tecnología"),
    ("https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "Economía"),
    ("https://feeds.npr.org/1001/rss.xml", "Mundo"),
    ("https://www.cbsnews.com/latest/rss/main", "Mundo"),
    ("https://feeds.nbcnews.com/nbcnews/public/news", "Mundo"),
    ("https://www.pbs.org/newshour/feeds/rss/headlines", "Mundo"),
    ("https://moxie.foxnews.com/google-publisher/latest.xml", "Mundo"),
    ("https://news.google.com/rss/search?q=when:24h+site:apnews.com&hl=en-US&gl=US&ceid=US:en", "Mundo"),
    # México: medios nacionales
    ("https://www.eluniversal.com.mx/seccion/1671/rss.xml", "Sociedad"),
    ("https://www.excelsior.com.mx/rss.xml", "Sociedad"),
    ("https://www.elfinanciero.com.mx/arc/outboundfeeds/rss/?outputType=xml", "Economía"),
    ("https://vanguardia.com.mx/rss.xml", "Sociedad"),
    # Internacional, tecnología, ciencia y deportes
    ("https://feeds.bbci.co.uk/mundo/rss.xml", "Mundo"),
    ("https://www.theguardian.com/world/rss", "Mundo"),
    ("https://techcrunch.com/feed/", "Tecnología"),
    ("https://www.theverge.com/rss/index.xml", "Tecnología"),
    ("https://feeds.bbci.co.uk/sport/rss.xml", "Deportes"),
    ("https://www.sciencedaily.com/rss/all.xml", "Ciencia"),
    ("https://www.economist.com/finance-and-economics/rss.xml", "Economía"),
]
ZONA_AR = timezone(timedelta(hours=-3))


def cargar_noticias():
    if not os.path.exists(NEWS_FILE_PATH):
        return []
    with open(NEWS_FILE_PATH, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            print("news.json corrupto: no se modifica para evitar pérdida de datos.")
            sys.exit(1)


def guardar_noticias(noticias):
    os.makedirs(os.path.dirname(NEWS_FILE_PATH), exist_ok=True)
    with open(NEWS_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(noticias, f, ensure_ascii=False, indent=2)
        f.write("\n")


def limpiar_html(texto):
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", html.unescape(texto)).strip()


def imagen_de_entrada(entry):
    for m in entry.get("media_content", []) + entry.get("media_thumbnail", []):
        if m.get("url"):
            return m["url"]
    for enc in entry.get("enclosures", []):
        if enc.get("type", "").startswith("image") and enc.get("href"):
            return enc["href"]
    return IMAGEN_POR_DEFECTO


def fecha_de_entrada(entry, hoy):
    try:
        from time import gmtime, strftime
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed:
            return strftime("%Y-%m-%d", parsed)
    except Exception:
        pass
    return hoy


def reescribir_con_ia(client, titulo, texto):
    prompt = f'''Eres editor de un portal de noticias en español. Resume y reescribe fielmente, sin inventar datos.
Devuelve solo JSON con title, summary, content y category. Categorías permitidas: Tecnología, Tendencias, Economía, Sociedad, Deportes, Mundo, Ciencia.
Título original: {titulo}\nTexto original: {texto}'''
    try:
        r = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}, temperature=0.4,
        )
        return json.loads(r.choices[0].message.content)
    except Exception as e:
        print(f"IA no disponible para esta nota; se usará el RSS: {e}")
        return None


def ejecutar():
    client = None
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
        except Exception as e:
            print(f"No se pudo iniciar OpenAI; continuaré sin IA: {e}")
    else:
        print("OPENAI_API_KEY no configurada: se importarán noticias RSS sin reescritura por IA.")

    noticias = cargar_noticias()
    ids = {str(n.get("id", "")) for n in noticias}
    urls = {n.get("sourceUrl") for n in noticias if n.get("sourceUrl")}
    titulos = {limpiar_html(n.get("title", "")).casefold() for n in noticias}
    hoy = datetime.now(ZONA_AR).strftime("%Y-%m-%d")
    agregadas = 0

    for url, categoria_default in RSS_FEEDS:
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": "PanoramaGlobalNews/1.0 (+RSS reader)"})
            if getattr(feed, "bozo", False):
                print(f"Aviso leyendo feed {url}: {getattr(feed, 'bozo_exception', 'feed no estándar')}")
        except Exception as e:
            print(f"No se pudo leer {url}: {e}")
            continue
        nuevas_de_fuente = 0
        for entry in feed.entries:
            if nuevas_de_fuente >= POR_FUENTE:
                break
            titulo = limpiar_html(entry.get("title", ""))
            enlace = entry.get("link", "")
            resumen = limpiar_html(entry.get("summary", "") or entry.get("description", ""))
            if not titulo or (enlace and enlace in urls) or titulo.casefold() in titulos:
                continue
            datos = reescribir_con_ia(client, titulo, resumen or titulo) if client else None
            nid = hashlib.sha1((enlace or (titulo + url)).encode("utf-8")).hexdigest()[:12]
            if nid in ids:
                continue
            # Sin IA se conserva el titular y el texto del feed: no se inventa contenido.
            category = (datos or {}).get("category") or categoria_default
            allowed = {"Tecnología", "Tendencias", "Economía", "Sociedad", "Deportes", "Mundo", "Ciencia"}
            if category not in allowed:
                category = categoria_default
            noticias.append({
                "id": nid,
                "title": limpiar_html((datos or {}).get("title") or titulo),
                "summary": limpiar_html((datos or {}).get("summary") or resumen or titulo),
                "content": limpiar_html((datos or {}).get("content") or resumen or titulo),
                "source": limpiar_html(feed.feed.get("title", "Fuente RSS"))[:100],
                "sourceUrl": enlace,
                "date": fecha_de_entrada(entry, hoy),
                "category": category,
                "imageUrl": imagen_de_entrada(entry),
            })
            ids.add(nid); titulos.add(titulo.casefold())
            if enlace: urls.add(enlace)
            agregadas += 1; nuevas_de_fuente += 1

    noticias.sort(key=lambda n: (n.get("date", ""), str(n.get("id", ""))), reverse=True)
    guardar_noticias(noticias[:MAX_NOTICIAS])
    print(f"Proceso terminado: {agregadas} noticias nuevas; total guardado: {min(len(noticias), MAX_NOTICIAS)}.")
    if agregadas == 0:
        print("No se encontraron notas nuevas. Revisar feeds o ejecutar de nuevo más tarde.")

if __name__ == "__main__":
    ejecutar()
