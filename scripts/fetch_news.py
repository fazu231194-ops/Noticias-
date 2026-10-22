import hashlib
import html
import json
import os
import re
import time
import calendar
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser
import trafilatura
import google.generativeai as genai

# Configuración de Gemini
API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
MODELO_IA = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

if API_KEY:
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODELO_IA)
else:
    model = None

NEWS_FILE_PATH = "src/data/news.json"
MAX_NOTICIAS = 300
POR_FUENTE = 2
HORAS_MAXIMAS = 48
MIN_TEXTO_BASE = 200

MAX_IA_POR_EJECUCION = 40
PAUSA_ENTRE_LLAMADAS = 7
REINTENTOS_IA = 3

estado_ia = {
    "llamadas": 0,
    "fallos_seguidos": 0,
    "cuota_agotada": False,
}

UTC = timezone.utc
ZONA_AR = timezone(timedelta(hours=-3))

IMAGEN_POR_DEFECTO = (
    "https://images.unsplash.com/"
    "photo-1504711434969-e33886168f5c"
    "?auto=format&fit=crop&w=800&q=80"
)

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

    # México
    ("https://www.eluniversal.com.mx/seccion/1671/rss.xml", "Sociedad"),
    ("https://www.excelsior.com.mx/rss.xml", "Sociedad"),
    ("https://www.elfinanciero.com.mx/arc/outboundfeeds/rss/?outputType=xml", "Economía"),

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

CATEGORIAS_VALIDAS = {
    "Mundo",
    "Sociedad",
    "Economía",
    "Tecnología",
    "Deportes",
    "Ciencia",
}

FUENTES_DEMO = {
    "techdaily",
    "webnews global",
    "economía hoy",
    "planeta urbano",
    "deportes total",
}

FRASES_DEMO = (
    "revoluciona la inteligencia artificial este año",
    "tendencias globales en el desarrollo web moderno",
    "mercados regionales cierran la semana",
    "ciudades apuestan por corredores verdes",
    "final electrizante corona al nuevo campeón",
)

PROMPT = """Sos un editor de un portal de noticias en español.
A partir del TEXTO BASE, escribí una nota NUEVA con tus propias palabras.

REGLAS:
- Escribí siempre en español neutro.
- Usá solo datos que estén en el texto base.
- No inventes cifras, nombres ni citas.
- No copies frases extensas del texto base.
- Extensión: entre 120 y 200 palabras.
- Ignorá menús, publicidad y enlaces a otras notas.
- Si no contiene una noticia real, devolvé articulo vacío.

Elegí categoria entre: Mundo, Sociedad, Economía,
Tecnología, Deportes, Ciencia.

Devolvé SOLO un JSON con estas claves:
{"titulo":"título en español",
 "resumen":"1 o 2 oraciones",
 "categoria":"una categoría válida",
 "articulo":"texto de la nota"}

TÍTULO ORIGINAL: __TITULO__

TEXTO BASE:
__TEXTO__
"""


def limpiar_html(texto):
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", html.unescape(texto)).strip()


def fecha_publicacion(entry):
    for campo in (
        "published_parsed",
        "updated_parsed",
        "created_parsed",
    ):
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
                try:
                    fecha = datetime.fromisoformat(
                        valor.replace("Z", "+00:00")
                    )
                    if fecha.tzinfo is None:
                        fecha = fecha.replace(tzinfo=UTC)
                    return fecha.astimezone(UTC)
                except (ValueError, TypeError, OverflowError):
                    pass

    return None


def imagen_de_entrada(entry):
    for grupo in (
        entry.get("media_content", []),
        entry.get("media_thumbnail", []),
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


def obtener_contenido_completo(url):
    """Extrae texto de la fuente para procesarlo con la IA."""
    try:
        descargado = trafilatura.fetch_url(url)
        if descargado:
            texto = trafilatura.extract(descargado)
            if texto and len(texto) > MIN_TEXTO_BASE:
                return texto
    except Exception as error:
        print(f"Error al extraer web {url}: {error}")

    return None


def texto_util(texto):
    if not texto or len(texto) < MIN_TEXTO_BASE:
        return False

    if texto.startswith("Watch CBS News"):
        return False

    return True


def redactar_con_ia(titulo, contenido_base):
    """Redacta una noticia con Gemini o devuelve None si falla."""
    if model is None or estado_ia["cuota_agotada"]:
        return None

    prompt = (
        PROMPT.replace("__TITULO__", titulo)
        .replace("__TEXTO__", contenido_base[:6000])
    )

    for intento in range(1, REINTENTOS_IA + 1):
        if estado_ia["llamadas"] > 0:
            time.sleep(PAUSA_ENTRE_LLAMADAS)

        estado_ia["llamadas"] += 1

        try:
            respuesta = model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.4,
                },
            )

            texto = (
                (respuesta.text or "").strip()
                if respuesta
                else ""
            )

            texto = re.sub(
                r"^```(?:json)?\s*|\s*```$",
                "",
                texto,
            )

            datos = json.loads(texto)

            if isinstance(datos, dict):
                estado_ia["fallos_seguidos"] = 0
                return datos

        except Exception as error:
            mensaje = str(error)
            print(
                f"Error IA ({intento}/{REINTENTOS_IA}): "
                f"{mensaje}"
            )

            # Si se agotó la cuota, no repetir solicitudes inútiles.
            if any(
                palabra in mensaje.lower()
                for palabra in (
                    "429",
                    "quota",
                    "rate limit",
                    "resource_exhausted",
                )
            ):
                estado_ia["cuota_agotada"] = True
                estado_ia["fallos_seguidos"] += 1
                print(
                    "Cuota de Gemini agotada. "
                    "Se continuará con el contenido RSS."
                )
                return None

            if intento < REINTENTOS_IA:
                time.sleep(5 * intento)

    estado_ia["fallos_seguidos"] += 1
    return None


def cargar_noticias():
    if not os.path.exists(NEWS_FILE_PATH):
        return []

    try:
        with open(NEWS_FILE_PATH, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)

        return datos if isinstance(datos, list) else []

    except (json.JSONDecodeError, OSError) as error:
        print(f"Error leyendo noticias existentes: {error}")
        return []


def guardar_noticias(noticias):
    directorio = os.path.dirname(NEWS_FILE_PATH)
    os.makedirs(directorio, exist_ok=True)

    temporal = NEWS_FILE_PATH + ".tmp"

    with open(temporal, "w", encoding="utf-8") as archivo:
        json.dump(
            noticias,
            archivo,
            ensure_ascii=False,
            indent=2,
        )
        archivo.write("\n")

    os.replace(temporal, NEWS_FILE_PATH)


def es_noticia_demo(noticia):
    fuente = limpiar_html(
        noticia.get("source", "")
    ).casefold()

    titulo = limpiar_html(
        noticia.get("title", "")
    ).casefold()

    identificador = str(noticia.get("id", ""))

    if (
        fuente in FUENTES_DEMO
        or identificador in {"1", "2", "3", "4", "5"}
    ):
        return True

    return any(
        frase in titulo
        for frase in FRASES_DEMO
    )


def convertir_fecha(texto):
    if not texto:
        return None

    try:
        texto = str(texto).strip()

        if "T" in texto:
            fecha = datetime.fromisoformat(
                texto.replace("Z", "+00:00")
            )
        else:
            fecha = datetime.strptime(
                texto[:10], "%Y-%m-%d"
            ).replace(tzinfo=UTC)

        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=UTC)

        return fecha.astimezone(UTC)

    except (ValueError, TypeError, OverflowError):
        return None


def ejecutar():
    ahora = datetime.now(UTC)
    limite = ahora - timedelta(hours=HORAS_MAXIMAS)

    if model is not None:
        print(f"IA configurada: {MODELO_IA}")
    else:
        print(
            "No hay clave de Gemini. "
            "Se intentará guardar noticias desde RSS."
        )

    anteriores = cargar_noticias()

    noticias = []
    urls = set()
    titulos = set()
    ids = set()

    # Conservar noticias recientes y evitar duplicados.
    for noticia in anteriores:
        if (
            not isinstance(noticia, dict)
            or es_noticia_demo(noticia)
        ):
            continue

        fecha = convertir_fecha(
            noticia.get("publishedAt")
            or noticia.get("date")
        )

        if (
            not fecha
            or fecha < limite
            or fecha > ahora + timedelta(minutes=5)
        ):
            continue

        enlace = noticia.get("sourceUrl", "").strip()

        titulo = limpiar_html(
            noticia.get("title", "")
        ).casefold()

        if (
            (enlace and enlace in urls)
            or (titulo and titulo in titulos)
        ):
            continue

        noticias.append(noticia)

        if enlace:
            urls.add(enlace)

        if titulo:
            titulos.add(titulo)

        if noticia.get("id"):
            ids.add(str(noticia["id"]))

    nuevas = 0
    fallos = 0

    # Aunque Gemini falle, el bot continúa leyendo RSS.
    for feed_url, categoria in RSS_FEEDS:
        try:
            feed = feedparser.parse(
                feed_url,
                request_headers={
                    "User-Agent": "PanoramaGlobalNews/1.0"
                },
            )
        except Exception as error:
            print(f"Error leyendo RSS {feed_url}: {error}")
            fallos += 1
            continue

        if not feed.entries:
            print(f"RSS sin entradas: {feed_url}")
            fallos += 1
            continue

        procesadas = 0

        for entry in feed.entries:
            if procesadas >= POR_FUENTE:
                break

            titulo = limpiar_html(
                entry.get("title", "")
            )

            enlace = entry.get("link", "").strip()

            resumen_rss = limpiar_html(
                entry.get("summary", "")
                or entry.get("description", "")
            )

            fecha = fecha_publicacion(entry)

            if not titulo or not enlace or not fecha:
                continue

            if (
                fecha < limite
                or fecha > ahora + timedelta(minutes=5)
            ):
                continue

            if (
                enlace in urls
                or titulo.casefold() in titulos
            ):
                continue

            identificador = hashlib.sha1(
                enlace.encode("utf-8")
            ).hexdigest()[:16]

            if identificador in ids:
                continue

            texto_crudo = (
                obtener_contenido_completo(enlace)
                or resumen_rss
                or titulo
            )

            if (
                not texto_util(texto_crudo)
                and len(resumen_rss) < 40
            ):
                print(
                    "Noticia omitida: no hay texto ni "
                    f"resumen suficiente: {titulo[:80]}"
                )
                continue

            datos = None

            # Intentar IA solo mientras esté disponible.
            if (
                model is not None
                and not estado_ia["cuota_agotada"]
                and estado_ia["llamadas"] < MAX_IA_POR_EJECUCION
            ):
                datos = redactar_con_ia(
                    titulo,
                    texto_crudo,
                )

            articulo = ""
            titulo_final = titulo
            resumen_corto = ""
            cat = categoria

            if datos:
                articulo_ia = re.sub(
                    r"<[^>]+>",
                    "",
                    str(datos.get("articulo") or ""),
                ).strip()

                if len(articulo_ia) >= 200:
                    articulo = articulo_ia[:4000]

                    titulo_final = (
                        limpiar_html(
                            str(datos.get("titulo") or "")
                        )
                        or titulo
                    )

                    resumen_corto = limpiar_html(
                        str(datos.get("resumen") or "")
                    )

                    cat = str(
                        datos.get("categoria") or ""
                    ).strip()

                    if cat not in CATEGORIAS_VALIDAS:
                        cat = categoria

            # Alternativa cuando la IA falla:
            # guardar el título y el resumen del RSS,
            # con enlace a la publicación original.
            if not articulo:
                resumen_corto = limpiar_html(
                    resumen_rss
                )[:300].rstrip()

                if len(resumen_corto) < 40:
                    print(
                        "Se omite por falta de resumen RSS: "
                        f"{titulo[:80]}"
                    )
                    continue

                articulo = (
                    resumen_corto
                    + "\n\nEsta noticia se basa en el "
                    "resumen publicado por la fuente original. "
                    "Consultá el enlace para leer la información "
                    "completa."
                )

                titulo_final = titulo
                cat = categoria

                print(
                    "Noticia guardada con RSS, sin IA: "
                    f"{titulo[:80]}"
                )

            if not resumen_corto:
                resumen_corto = (
                    limpiar_html(articulo)[:200] + "..."
                )

            noticia = {
                "id": identificador,
                "title": titulo_final[:300],
                "summary": resumen_corto[:300],
                "content": articulo[:4000],
                "source": limpiar_html(
                    feed.feed.get("title", "Fuente RSS")
                )[:100],
                "sourceUrl": enlace,
                "date": fecha.astimezone(
                    ZONA_AR
                ).strftime("%Y-%m-%d"),
                "publishedAt": fecha.isoformat(),
                "category": cat,
                "imageUrl": imagen_de_entrada(entry),
            }

            noticias.append(noticia)

            urls.add(enlace)
            titulos.add(titulo.casefold())
            titulos.add(titulo_final.casefold())
            ids.add(identificador)

            nuevas += 1
            procesadas += 1

    noticias.sort(
        key=lambda noticia: noticia.get(
            "publishedAt", ""
        ),
        reverse=True,
    )

    guardar_noticias(noticias[:MAX_NOTICIAS])

    print(
        f"Proceso terminado: {nuevas} noticias nuevas; "
        f"{min(len(noticias), MAX_NOTICIAS)} guardadas; "
        f"{estado_ia['llamadas']} llamadas a la IA; "
        f"{fallos} fuentes RSS con errores."
    )


if __name__ == "__main__":
    ejecutar()
