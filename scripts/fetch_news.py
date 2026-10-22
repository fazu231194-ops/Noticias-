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

# Configuración de la IA (Gemini)
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
MIN_TEXTO_BASE = 200  # caracteres mínimos para considerar que hay una noticia

# Límites para el plan gratuito de Gemini
MAX_IA_POR_EJECUCION = 40
PAUSA_ENTRE_LLAMADAS = 7  # segundos
REINTENTOS_IA = 3
MAX_FALLOS_SEGUIDOS = 3

estado_ia = {"llamadas": 0, "fallos_seguidos": 0}

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

CATEGORIAS_VALIDAS = {"Mundo", "Sociedad", "Economía", "Tecnología", "Deportes", "Ciencia"}

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
- Escribí siempre en español neutro, aunque el texto base esté en otro idioma.
- No copies frases del texto base: no repitas más de 6 palabras seguidas. Cambiá la estructura de las oraciones.
- Usá solo datos que estén en el texto base. No inventes cifras, nombres ni citas.
- No uses comillas salvo para una declaración textual muy breve (máximo 12 palabras).
- Extensión del artículo: entre 120 y 200 palabras, en 2 o 3 párrafos separados por una línea en blanco.
- Ignorá menús, publicidad, enlaces a otras notas, "minutos de lectura" y textos de videos.
- Si el texto base no contiene una noticia real (solo menús, un video o contenido vacío), devolvé "articulo" vacío.

Elegí "categoria" entre: Mundo, Sociedad, Economía, Tecnología, Deportes, Ciencia.

Devolvé SOLO un JSON con estas claves:
{"titulo": "título en español, máximo 120 caracteres, con tus palabras",
 "resumen": "1 o 2 oraciones, máximo 200 caracteres",
 "categoria": "una de las categorías",
 "articulo": "el texto de la nota"}

TÍTULO ORIGINAL: __TITULO__

TEXTO BASE:
__TEXTO__
"""


def limpiar_html(texto):
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", html.unescape(texto)).strip()


def fecha_publicacion(entry):
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
                try:
                    fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
                    if fecha.tzinfo is None:
                        fecha = fecha.replace(tzinfo=UTC)
                    return fecha.astimezone(UTC)
                except (ValueError, TypeError, OverflowError):
                    pass
    return None


def imagen_de_entrada(entry):
    for grupo in (entry.get("media_content", []), entry.get("media_thumbnail", [])):
        for media in grupo:
            if media.get("url"):
                return media["url"]

    for enclosure in entry.get("enclosures", []):
        if enclosure.get("type", "").startswith("image") and enclosure.get("href"):
            return enclosure["href"]

    return IMAGEN_POR_DEFECTO


def obtener_contenido_completo(url):
    """Descarga la noticia original y extrae el texto limpio (solo para que la IA lo lea)."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            texto_extraido = trafilatura.extract(downloaded)
            if texto_extraido and len(texto_extraido) > 200:
                return texto_extraido
    except Exception as e:
        print(f"Error al extraer web {url}: {e}")
    return None


def texto_util(texto):
    """Descarta textos vacíos o con restos de menús de video."""
    if not texto or len(texto) < MIN_TEXTO_BASE:
        return False
    if texto.startswith("Watch CBS News"):
        return False
    return True


def redactar_con_ia(titulo, contenido_base):
    """Pide a Gemini una nota nueva en JSON. Devuelve un dict, o None si la IA falla."""
    prompt = PROMPT.replace("__TITULO__", titulo).replace("__TEXTO__", contenido_base[:6000])

    for intento in range(1, REINTENTOS_IA + 1):
        if estado_ia["llamadas"] > 0:
            time.sleep(PAUSA_ENTRE_LLAMADAS)
        estado_ia["llamadas"] += 1
        try:
            response = model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.4,
                },
            )
            texto = (response.text or "").strip() if response else ""
            texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)
            datos = json.loads(texto)
            if isinstance(datos, dict):
                estado_ia["fallos_seguidos"] = 0
                return datos
        except Exception as e:
            print(f"Error al generar con IA (intento {intento}/{REINTENTOS_IA}): {e}")
            time.sleep(20 * intento)

    estado_ia["fallos_seguidos"] += 1
    return None


def cargar_noticias():
    if not os.path.exists(NEWS_FILE_PATH):
        return []
    try:
        with open(NEWS_FILE_PATH, "r", encoding="utf-8") as archivo:
            data = json.load(archivo)
        if not isinstance(data, list):
            return []
        return data
    except json.JSONDecodeError:
        return []


def guardar_noticias(noticias):
    directorio = os.path.dirname(NEWS_FILE_PATH)
    os.makedirs(directorio, exist_ok=True)
    temporal = NEWS_FILE_PATH + ".tmp"
    with open(temporal, "w", encoding="utf-8") as archivo:
        json.dump(noticias, archivo, ensure_ascii=False, indent=2)
        archivo.write("\n")
    os.replace(temporal, NEWS_FILE_PATH)


def es_noticia_demo(noticia):
    fuente = limpiar_html(noticia.get("source", "")).casefold()
    titulo = limpiar_html(noticia.get("title", "")).casefold()
    identificador = str(noticia.get("id", ""))
    if fuente in FUENTES_DEMO or identificador in {"1", "2", "3", "4", "5"}:
        return True
    return any(frase in titulo for frase in FRASES_DEMO)


def convertir_fecha(texto):
    if not texto:
        return None
    try:
        texto = str(texto).strip()
        if "T" in texto:
            fecha = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        else:
            fecha = datetime.strptime(texto[:10], "%Y-%m-%d").replace(tzinfo=UTC)
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=UTC)
        return fecha.astimezone(UTC)
    except (ValueError, TypeError, OverflowError):
        return None


def ejecutar():
    ahora = datetime.now(UTC)
    limite = ahora - timedelta(hours=HORAS_MAXIMAS)

    if model:
        print(f"IA activada: {MODELO_IA}")
    else:
        print("ATENCIÓN: no hay clave de Gemini; no se guardarán noticias nuevas.")

    anteriores = cargar_noticias()
    noticias = []
    urls = set()
    titulos = set()
    ids = set()

    for noticia in anteriores:
        if not isinstance(noticia, dict) or es_noticia_demo(noticia):
            continue
        fecha = convertir_fecha(noticia.get("publishedAt") or noticia.get("date"))
        if not fecha or fecha < limite or fecha > ahora + timedelta(minutes=5):
            continue

        enlace = noticia.get("sourceUrl", "").strip()
        titulo = limpiar_html(noticia.get("title", "")).casefold()

        if (enlace and enlace in urls) or (titulo and titulo in titulos):
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
    detener = model is None  # sin IA no se agrega nada nuevo

    for feed_url, categoria in RSS_FEEDS:
        if detener:
            break

        try:
            feed = feedparser.parse(
                feed_url,
                request_headers={"User-Agent": "PanoramaGlobalNews/1.0"},
            )
        except Exception as error:
            print(f"ERROR leyendo {feed_url}: {error}")
            fallos += 1
            continue

        if not feed.entries:
            fallos += 1
            continue

        procesadas = 0

        for entry in feed.entries:
            if procesadas >= POR_FUENTE:
                break

            titulo = limpiar_html(entry.get("title", ""))
            enlace = entry.get("link", "").strip()
            resumen_rss = limpiar_html(entry.get("summary", "") or entry.get("description", ""))
            fecha = fecha_publicacion(entry)

            if not titulo or not enlace or not fecha:
                continue

            if fecha < limite or fecha > ahora + timedelta(minutes=5):
                continue

            if enlace in urls or titulo.casefold() in titulos:
                continue

            identificador = hashlib.sha1(enlace.encode("utf-8")).hexdigest()[:16]
            if identificador in ids:
                continue

            # 1. Leer el texto original (solo para que la IA lo use de base)
            texto_crudo = obtener_contenido_completo(enlace) or resumen_rss or titulo
            if not texto_util(texto_crudo):
                print(f"Sin texto útil, se omite: {titulo[:80]}")
                continue

            # 2. Límites de la IA en esta ejecución
            if (
                estado_ia["llamadas"] >= MAX_IA_POR_EJECUCION
                or estado_ia["fallos_seguidos"] >= MAX_FALLOS_SEGUIDOS
            ):
                print("Se alcanzó el límite de la IA en esta ejecución; el resto queda para la próxima.")
                detener = True
                break

            # 3. Redactar una nota nueva con la IA
            datos = redactar_con_ia(titulo, texto_crudo)
            if not datos:
                print(f"IA falló para: {titulo[:80]}")
                continue

            articulo = re.sub(r"<[^>]+>", "", str(datos.get("articulo") or "")).strip()
            if len(articulo) < 200:
                print(f"La IA no encontró una noticia real, se omite: {titulo[:80]}")
                continue

            titulo_final = limpiar_html(str(datos.get("titulo") or "")) or titulo
            resumen_corto = limpiar_html(str(datos.get("resumen") or ""))
            if not resumen_corto:
                resumen_corto = limpiar_html(articulo)[:200] + "..."

            cat = str(datos.get("categoria") or "").strip()
            if cat not in CATEGORIAS_VALIDAS:
                cat = categoria

            noticia = {
                "id": identificador,
                "title": titulo_final[:300],
                "summary": resumen_corto[:300],
                "content": articulo[:4000],
                "source": limpiar_html(feed.feed.get("title", "Fuente RSS"))[:100],
                "sourceUrl": enlace,
                "date": fecha.astimezone(ZONA_AR).strftime("%Y-%m-%d"),
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

    noticias.sort(key=lambda noticia: noticia.get("publishedAt", ""), reverse=True)
    guardar_noticias(noticias[:MAX_NOTICIAS])

    print(
        f"Proceso terminado: {nuevas} noticias nuevas; "
        f"{min(len(noticias), MAX_NOTICIAS)} guardadas; "
        f"{estado_ia['llamadas']} llamadas a la IA."
    )


if __name__ == "__main__":
    ejecutar()
