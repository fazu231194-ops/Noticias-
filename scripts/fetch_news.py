
import hashlib
import html
import json
import os
import re
import sys
import time
import calendar
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import feedparser

NEWS_FILE_PATH = "src/data/news.json"
MAX_NOTICIAS = 300
POR_FUENTE = 10
HORAS_MAXIMAS = 48

ZONA_AR = timezone(timedelta(hours=-3))
UTC = timezone.utc

IMAGEN_POR_DEFECTO = (
    "https://images.unsplash.com/photo-1504711434969-e33886168f5c"
    "?auto=format&fit=crop&w=800&q=80"
)

# Medios de Argentina, Estados Unidos, México y otros países.
RSS_FEEDS = [
    # Argentina
    ("https://www.lanacion.com.ar/arc/outboundfeeds/rss/?outputType=xml", "Sociedad"),
    ("https://www.clarin.com/rss/lo-ultimo/", "Sociedad"),
    ("https://www.infobae.com/feeds/rss/", "Mundo"),
    ("https://www.pagina12.com.ar/rss/portada", "Sociedad"),
    ("https://www.ambito.com/rss/pages/ambito.xml", "Economía"),

    # Estados Unidos
    ("https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "Mundo"),
    ("https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "Tecnología"),
    ("https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "Economía"),
    ("https://feeds.npr.org/1001/rss.xml", "Mundo"),
    ("https://www.cbsnews.com/latest/rss/main", "Mundo"),
    ("https://feeds.nbcnews.com/nbcnews/public/news", "Mundo"),
    ("https://www.pbs.org/newshour/feeds/rss/headlines", "Mundo"),
    ("https://moxie.foxnews.com/google-publisher/latest.xml", "Mundo"),

    # México
    ("https://www.eluniversal.com.mx/seccion/1671/rss.xml", "Sociedad"),
    ("https://www.excelsior.com.mx/rss.xml", "Sociedad"),
    ("https://www.elfinanciero.com.mx/arc/outboundfeeds/rss/?outputType=xml", "Economía"),
    ("https://vanguardia.com.mx/rss.xml", "Sociedad"),

    # Internacional
    ("https://feeds.bbci.co.uk/mundo/rss.xml", "Mundo"),
    ("https://www.theguardian.com/world/rss", "Mundo"),
    ("https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada", "Mundo"),

    # Tecnología, ciencia y deportes
    ("https://techcrunch.com/feed/", "Tecnología"),
    ("https://www.theverge.com/rss/index.xml", "Tecnología"),
    ("https://feeds.bbci.co.uk/sport/rss.xml", "Deportes"),
    ("https://www.sciencedaily.com/rss/all.xml", "Ciencia"),
]

CATEGORIAS = {
    "Tecnología", "Desarrollo", "Tendencias", "Economía",
    "Sociedad", "Deportes", "Mundo", "Ciencia"
}

# Identificadores y fuentes que corresponden a noticias ficticias.
FUENTES_DEMO = {
    "techdaily", "webnews global", "economía hoy",
    "planeta urbano", "deportes total"
}


def limpiar_html(texto):
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", html.unescape(texto)).strip()


def fecha_publicacion(entry):
    """Devuelve la fecha real del feed, convertida a UTC."""
    for campo in ("published_parsed", "updated_parsed", "created_parsed"):
        valor = entry.get(campo)
        if valor:
            try:
                segundos = calendar.timegm(valor)
                return datetime.fromtimestamp(segundos, tz=UTC)
            except (ValueError, TypeError, OverflowError):
                pass

    for campo in ("published", "updated", "created"):
        valor = entry.get(campo)
        if valor:
            try:
                fecha = parsedate_to_datetime(valor)
                if fecha.tzinfo is None:
                    fecha = fecha.replace(tzinfo=UTC)
                return fecha.astimezone(UTC)
            except (ValueError, TypeError, OverflowError):
                pass

    return None


def imagen_de_entrada(entry):
    for grupo in (
        entry.get("media_content", []),
        entry.get("media_thumbnail", [])
    ):
        for media in grupo:
            if media.get("url"):
                return media["url"]

    for enclosure in entry.get("enclosures", []):
        if (
            enclosure.get("type", "").startswith("image")
            and enclosure.get("href")
        ):
            return enclosure["href"]

    return IMAGEN_POR_DEFECTO


def cargar_noticias():
    if not os.path.exists(NEWS_FILE_PATH):
        return []

    try:
        with open(NEWS_FILE_PATH, "r", encoding="utf-8") as archivo:
            data = json.load(archivo)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        print("ERROR: news.json contiene JSON inválido. No se modificó.")
        sys.exit(1)


def guardar_noticias(noticias):
    directorio = os.path.dirname(NEWS_FILE_PATH)
    os.makedirs(directorio, exist_ok=True)

    temporal = NEWS_FILE_PATH + ".tmp"
    with open(temporal, "w", encoding="utf-8") as archivo:
        json.dump(noticias, archivo, ensure_ascii=False, indent=2)
        archivo.write("\n")

    os.replace(temporal, NEWS_FILE_PATH)


def reescribir_con_ia(client, titulo, resumen, categoria):
    """Reescribe solo la información disponible, sin inventar hechos."""
    prompt = f"""
Actuás como editor periodístico de un portal de noticias en español.
Reescribí el material con palabras originales, sin copiar frases extensas.
No inventes cifras, citas, nombres, lugares ni hechos que no estén en
el material recibido. Si el material es insuficiente, hacé un resumen
prudente y breve. No afirmes que conocés información que no aparece aquí.

Devolvé exclusivamente un objeto JSON con:
title: titular claro y original.
summary: resumen breve.
content: nota breve basada únicamente en el material suministrado.
category: una de Tecnología, Desarrollo, Tendencias, Economía,
Sociedad, Deportes, Mundo o Ciencia.

Categoría sugerida: {categoria}
Titular de origen: {titulo}
Extracto disponible: {resumen[:6000]}
"""
    try:
        respuesta = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=900,
        )

        datos = json.loads(respuesta.choices[0].message.content or "{}")

        titulo_nuevo = limpiar_html(datos.get("title", ""))
        resumen_nuevo = limpiar_html(datos.get("summary", ""))
        contenido_nuevo = limpiar_html(datos.get("content", ""))
        categoria_nueva = limpiar_html(datos.get("category", ""))

        if not titulo_nuevo or not resumen_nuevo or not contenido_nuevo:
            return None

        if categoria_nueva not in CATEGORIAS:
            categoria_nueva = categoria

        return {
            "title": titulo_nuevo[:300],
            "summary": resumen_nuevo[:1000],
            "content": contenido_nuevo[:6000],
            "category": categoria_nueva,
        }

    except Exception as error:
        print(f"AVISO: no se pudo reescribir con IA: {error}")
        return None


def es_noticia_demo(noticia):
    fuente = limpiar_html(noticia.get("source", "")).casefold()
    titulo = limpiar_html(noticia.get("title", "")).casefold()

    if fuente in FUENTES_DEMO:
        return True

    if str(noticia.get("id", "")) in {"1", "2", "3", "4", "5"}:
        # Los IDs numéricos antiguos corresponden a la muestra inicial.
        return True

    frases_demo = (
        "revoluciona la inteligencia artificial este año",
        "tendencias globales en el desarrollo web moderno",
        "mercados regionales cierran la semana",
        "ciudades apuestan por corredores verdes",
        "final electrizante corona al nuevo campeón",
    )
    return any(frase in titulo for frase in frases_demo)


def ejecutar():
    ahora = datetime.now(UTC)
    limite = ahora - timedelta(hours=HORAS_MAXIMAS)

    client = None
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()

    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            print("API de OpenAI configurada.")
        except Exception as error:
            print(f"ERROR iniciando OpenAI: {error}")
    else:
        print("AVISO: falta OPENAI_API_KEY. Se guardarán extractos RSS sin reescritura.")

    anteriores = cargar_noticias()

    # Quita ejemplos y noticias antiguas. Conserva registros recientes
    # que tengan fecha interpretable.
    noticias = []
    ids = set()
    urls = set()
    titulos = set()

    for noticia in anteriores:
        if not isinstance(noticia, dict) or es_noticia_demo(noticia):
            continue

        fecha_texto = noticia.get("publishedAt") or noticia.get("date", "")
        fecha = None

        try:
            if "T" in str(fecha_texto):
                fecha = datetime.fromisoformat(
                    str(fecha_texto).replace("Z", "+00:00")
                )
                if fecha.tzinfo is None:
                    fecha = fecha.replace(tzinfo=UTC)
                fecha = fecha.astimezone(UTC)
            elif fecha_texto:
                fecha = datetime.strptime(
                    str(fecha_texto)[:10], "%Y-%m-%d"
                ).replace(tzinfo=UTC)
        except (ValueError, TypeError):
            fecha = None

        if not fecha or fecha < limite or fecha > ahora + timedelta(minutes=5):
            continue

        noticia["publishedAt"] = fecha.isoformat()
        noticia["date"] = fecha.astimezone(ZONA_AR).strftime("%Y-%m-%d")

        nid = str(noticia.get("id", ""))
        enlace = noticia.get("sourceUrl", "")
        titulo = limpiar_html(noticia.get("title", "")).casefold()

        if nid:
            ids.add(nid)
        if enlace:
            urls.add(enlace)
        if titulo:
            titulos.add(titulo)

        noticias.append(noticia)

    nuevas = 0
    fallos = 0

    for feed_url, categoria_default in RSS_FEEDS:
        try:
            feed = feedparser.parse(
                feed_url,
                request_headers={
                    "User-Agent": "PanoramaGlobalNews/1.0 (RSS reader)"
                },
            )
        except Exception as error:
            print(f"ERROR leyendo feed {feed_url}: {error}")
            fallos += 1
            continue

        if not feed.entries:
            print(f"AVISO: el feed no devolvió noticias: {feed_url}")
            fallos += 1
            continue

        procesadas = 0

        for entry in feed.entries:
            if procesadas >= POR_FUENTE:
                break

            titulo = limpiar_html(entry.get("title", ""))
            enlace = entry.get("link", "").strip()
            resumen = limpiar_html(
                entry.get("summary", "") or entry.get("description", "")
            )
            fecha = fecha_publicacion(entry)

            if not titulo or not enlace or not fecha:
                continue

            # No publicar como nueva una nota antigua ni una fecha futura.
            if fecha < limite or fecha > ahora + timedelta(minutes=5):
                continue

            if enlace in urls or titulo.casefold() in titulos:
                continue

            nid = hashlib.sha1(enlace.encode("utf-8")).hexdigest()[:16]
            if nid in ids:
                continue

            procesadas += 1
            datos = (
                reescribir_con_ia(client, titulo, resumen or titulo, categoria_default)
                if client else None
            )

            # Si la API falla, se conserva el titular y el extracto original
            # del feed. No se inventa una noticia.
            fecha_local = fecha.astimezone(ZONA_AR)

            noticia = {
                "id": nid,
                "title": (datos or {}).get("title") or titulo,
                "summary": (datos or {}).get("summary") or resumen or titulo,
                "content": (datos or {}).get("content") or resumen or titulo,
                "source": limpiar_html(feed.feed.get("title", "Fuente RSS"))[:100],
                "sourceUrl": enlace,
                "date": fecha_local.strftime("%Y-%m-%d"),
                "publishedAt": fecha.isoformat(),
                "category": (datos or {}).get("category") or categoria_default,
                "imageUrl": imagen_de_entrada(entry),
            }

            noticias.append(noticia)
            ids.add(nid)
            urls.add(enlace)
            titulos.add(titulo.casefold())
            nuevas += 1

        print(f"Feed revisado: {feed_url}; nuevas procesadas: {procesadas}")

    # Más recientes primero.
    noticias.sort(
        key=lambda n: n.get("publishedAt", ""),
        reverse=True,
    )

    guardar_noticias(noticias[:MAX_NOTICIAS])

    print(
        f"Proceso terminado: {nuevas} noticias nuevas; "
        f"{min(len(noticias), MAX_NOTICIAS)} noticias guardadas; "
        f"{fallos} feeds sin resultados."
    )

    if client is None:
        print("IMPORTANTE: las noticias nuevas no se reescribieron con IA.")
    if nuevas == 0:
        print("No se encontraron noticias nuevas dentro de las últimas 48 horas.")


if __name__ == "__main__":
    ejecutar()
