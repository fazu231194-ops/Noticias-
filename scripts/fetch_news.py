"""Genera notas para Panorama Global News a partir de feeds RSS y las guarda en src/data/news.json."""
import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import feedparser
from openai import OpenAI

NEWS_FILE_PATH = "src/data/news.json"
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
MAX_NOTICIAS = 100          # tope de notas guardadas
POR_FUENTE = 2              # notas nuevas por feed y ejecución
IMAGEN_POR_DEFECTO = (
    "https://images.unsplash.com/photo-1504711434969-e33886168f5c?auto=format&fit=crop&w=800&q=80"
)

RSS_FEEDS = [
    "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/tecnologia",
    "https://cnnespanol.cnn.com/feed/",
    "https://feeds.bbci.co.uk/mundo/rss.xml",
    # Medios de EE. UU. (en inglés: la IA los traduce y reescribe al español)
    "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://feeds.npr.org/1001/rss.xml",
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
]

ZONA_AR = timezone(timedelta(hours=-3))


def cargar_noticias():
    if not os.path.exists(NEWS_FILE_PATH):
        return []
    with open(NEWS_FILE_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            print("news.json corrupto: no se toca para no perder datos.")
            sys.exit(1)


def guardar_noticias(noticias):
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


def reescribir_con_enfoque_viral(client, titulo_original, contenido_original):
    prompt = f"""
Eres el editor jefe de 'Panorama Global News', un diario enfocado en noticias de alto impacto y tecnología.
Reescribe la siguiente noticia con un ángulo atractivo, periodístico y moderno que invite a leerla completa.
Reglas: no inventes datos, cifras, citas ni nombres que no estén en el texto original; destaca lo más
impactante sin exagerar ni mentir; la noticia puede venir en inglés: tradúcela y redáctala con tus propias palabras, en español neutro.
Devuelve únicamente un JSON con estas claves:
- "title": titular potente y llamativo.
- "summary": un párrafo de introducción que enganche al lector.
- "content": desarrollo de la noticia, limpio y original, basado solo en el texto dado.
- "category": una de Tecnología, Tendencias, Economía, Sociedad, Deportes, Mundo, Ciencia.

Noticia original:
Título: {titulo_original}
Texto: {contenido_original}
"""
    try:
        r = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.7,
        )
        return json.loads(r.choices[0].message.content)
    except Exception as e:  # noqa: BLE001
        print(f"Error con la IA: {e}")
        return None


def ejecutar():
    if not os.environ.get("OPENAI_API_KEY"):
        print("Falta la variable OPENAI_API_KEY (secreto del repositorio).")
        sys.exit(1)
    client = OpenAI()

    noticias = cargar_noticias()
    vistos = {n["title"] for n in noticias}
    ids = {n["id"] for n in noticias}
    hoy = datetime.now(ZONA_AR).strftime("%Y-%m-%d")
    agregadas = 0

    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
        except Exception as e:  # noqa: BLE001
            print(f"No se pudo leer {url}: {e}")
            continue

        nuevas_de_fuente = 0
        for entry in feed.entries:
            if nuevas_de_fuente >= POR_FUENTE:
                break
            titulo = limpiar_html(entry.get("title", ""))
            enlace = entry.get("link", "")
            resumen = limpiar_html(entry.get("summary", ""))
            if not titulo or titulo in vistos:
                continue

            datos = reescribir_con_enfoque_viral(client, titulo, resumen or titulo)
            if not datos:
                continue

            nid = hashlib.sha1((enlace or titulo).encode("utf-8")).hexdigest()[:10]
            if nid in ids:
                continue
            noticias.insert(0, {
                "id": nid,
                "title": datos.get("title") or titulo,
                "summary": datos.get("summary") or resumen,
                "content": datos.get("content") or resumen,
                "source": "Panorama Global News (Redacción)",
                "date": hoy,
                "category": datos.get("category") or "Tendencias",
                "imageUrl": imagen_de_entrada(entry),
            })
            vistos.add(titulo)
            ids.add(nid)
            agregadas += 1
            nuevas_de_fuente += 1

    # Más nuevas primero (orden estable) y recorte de las más antiguas
    noticias.sort(key=lambda n: n["date"], reverse=True)
    guardar_noticias(noticias[:MAX_NOTICIAS])
    print(f"¡Listo! Se añadieron {agregadas} notas.")


if __name__ == "__main__":
    ejecutar()
