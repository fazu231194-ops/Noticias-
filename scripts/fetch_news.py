
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

# =========================
# CONFIGURACIÓN DE GEMINI
# =========================

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
MODELO_IA = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

if API_KEY:
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODELO_IA)
else:
    model = None

# =========================
# CONFIGURACIÓN GENERAL
# =========================

NEWS_FILE_PATH = "src/data/news.json"
PENDING_FILE_PATH = "src/data/pending_news.json"

MAX_NOTICIAS = 300
POR_FUENTE = 2
HORAS_MAXIMAS = 48
MIN_TEXTO_BASE = 200

# Cuota prudente: no gastar todas las llamadas diarias
MAX_IA_POR_EJECUCION = 5
PAUSA_ENTRE_LLAMADAS = 7
REINTENTOS_IA = 1

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
    ("https://www.lanacion.com.ar/arc/outboundfeeds/rss/?outputType=xml", "Sociedad"),
    ("https://www.clarin.com/rss/lo-ultimo/", "Sociedad"),
    ("https://www.infobae.com/feeds/rss/", "Mundo"),
    ("https://www.pagina12.com.ar/rss/portada", "Sociedad"),
    ("https://www.ambito.com/rss/pages/ambito.xml", "Economía"),

    ("https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "Mundo"),
    ("https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "Tecnología"),
    ("https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "Economía"),
    ("https://feeds.npr.org/1001/rss.xml", "Mundo"),
    ("https://www.cbsnews.com/latest/rss/main", "Mundo"),
    ("https://feeds.nbcnews.com/nbcnews/public/news", "Mundo"),

    ("https://www.eluniversal.com.mx/seccion/1671/rss.xml", "Sociedad"),
    ("https://www.excelsior.com.mx/rss.xml", "Sociedad"),
    ("https://www.elfinanciero.com.mx/arc/outboundfeeds/rss/?outputType=xml", "Economía"),

    ("https://feeds.bbci.co.uk/mundo/rss.xml", "Mundo"),
    ("https://www.theguardian.com/world/rss", "Mundo"),
    ("https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada", "Mundo"),

    ("https://techcrunch.com/feed/", "Tecnología"),
    ("https://www.theverge.com/rss/index.xml", "Tecnología"),
    ("https://feeds.bbci.co.uk/sport/rss.xml", "Deportes"),
    ("https://www.sciencedaily.com/rss/all.xml", "Ciencia"),
]

CATEGORIAS_VALIDAS = {
    "Mundo", "Sociedad", "Economía",
    "Tecnología", "Deportes", "Ciencia",
}

FUENTES_DEMO = {
    "techdaily", "webnews global", "economía hoy",
    "planeta urbano", "deportes total",
}

FRASES_DEMO = (
    "revoluciona la inteligencia artificial este año",
    "tendencias globales en el desarrollo web moderno",
    "mercados regionales cierran la semana",
    "ciudades apuestan por corredores verdes",
    "final electrizante corona al nuevo campeón",
)

# La IA debe analizar la información y redactar una pieza periodística nueva.
PROMPT = """Sos periodista y editor de Noticias Globales.

Leé y comprendé el material de origen. Identificá los hechos principales,
quiénes participaron, qué ocurrió, cuándo y dónde, los antecedentes
disponibles y las consecuencias que estén respaldadas por la información.

Después redactá una NOTA PERIODÍSTICA ORIGINAL desde cero. No hagas una
paráfrasis mecánica ni cambies solamente palabras por sinónimos.
Organizá los hechos con una estructura propia, un título nuevo y una
introducción clara que explique la noticia.

EXTENSIÓN:
- Objetivo de 800 a 1.200 palabras si la información lo permite.
- Desarrollá la noticia en varios párrafos y usá subtítulos cuando ayuden.
- No entregues solamente un resumen breve.
- No repitas ideas para alargar artificialmente el texto.
- Si la fuente no contiene información suficiente, escribí una nota
  completa dentro de lo que se puede confirmar, sin inventar datos.

PRECISIÓN:
- Escribí en español neutro.
- Conservá nombres, fechas, lugares, cifras y hechos importantes.
- No inventes declaraciones, citas, estadísticas ni antecedentes.
- Diferenciá los hechos confirmados de las posibilidades o interpretaciones.
- No presentes inferencias como hechos.
- No reproduzcas párrafos de la fuente. Las citas breves necesarias deben
  estar claramente atribuidas.
- Ignorá menús, publicidad y enlaces a otras notas.
- Si el texto no contiene una noticia real, devolvé articulo vacío.

Elegí categoria entre: Mundo, Sociedad, Economía, Tecnología, Deportes,
Ciencia.

Devolvé SOLO un JSON válido con estas claves:
{
  "titulo": "título original en español",
  "resumen": "resumen de 1 o 2 oraciones",
  "categoria": "una categoría válida",
  "articulo": "artículo completo en texto plano"
}

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
    """Extrae el texto de origen para que la IA lo analice."""
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
    return bool(
        texto
        and len(texto.strip()) >= MIN_TEXTO_BASE
        and not texto.strip().startswith("Watch CBS News")
    )


def es_error_cuota(error):
    mensaje = str(error).lower()
    return any(p in mensaje for p in (
        "429", "quota", "rate limit",
        "resource_exhausted", "too many requests",
    ))


def redactar_con_ia(titulo, contenido_base):
    """Devuelve un artículo generado por Gemini o None si no fue posible."""
    if model is None or estado_ia["cuota_agotada"]:
        return None

    if estado_ia["llamadas"] >= MAX_IA_POR_EJECUCION:
        print("Límite de llamadas a Gemini alcanzado.")
        return None

    prompt = (
        PROMPT.replace("__TITULO__", titulo)
        .replace("__TEXTO__", contenido_base[:18000])
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
                    "temperature": 0.5,
                    "max_output_tokens": 8192,
                },
            )

            texto = (respuesta.text or "").strip() if respuesta else ""
            texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)

            datos = json.loads(texto)

            if not isinstance(datos, dict):
                raise ValueError("La respuesta de Gemini no es un objeto JSON.")

            articulo = str(datos.get("articulo") or "").strip()
            if len(articulo) < 200:
                print("Gemini devolvió un artículo demasiado corto o vacío.")
                return None

            estado_ia["fallos_seguidos"] = 0
            return datos

        except Exception as error:
            print(f"Error IA ({intento}/{REINTENTOS_IA}): {error}")

            if es_error_cuota(error):
                estado_ia["cuota_agotada"] = True
                print("Cuota de Gemini agotada. Se pausa la redacción por IA.")
                return None

            if intento < REINTENTOS_IA:
                time.sleep(5 * intento)

    estado_ia["fallos_seguidos"] += 1
    return None


def cargar_json(ruta, valor_predeterminado):
    if not os.path.exists(ruta):
        return valor_predeterminado
    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            return json.load(archivo)
    except (json.JSONDecodeError, OSError) as error:
        print(f"Error leyendo {ruta}: {error}")
        return valor_predeterminado


def guardar_json(ruta, datos):
    directorio = os.path.dirname(ruta)
    if directorio:
        os.makedirs(directorio, exist_ok=True)

    temporal = ruta + ".tmp"
    with open(temporal, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2)
        archivo.write("\n")
    os.replace(temporal, ruta)


def cargar_noticias():
    datos = cargar_json(NEWS_FILE_PATH, [])
    return datos if isinstance(datos, list) else []


def guardar_noticias(noticias):
    guardar_json(NEWS_FILE_PATH, noticias)


def cargar_pendientes():
    datos = cargar_json(PENDING_FILE_PATH, [])
    return datos if isinstance(datos, list) else []


def guardar_pendientes(pendientes):
    guardar_json(PENDING_FILE_PATH, pendientes)


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


def preparar_noticia(datos, pendiente):
    """Convierte una respuesta válida de Gemini en el formato del sitio."""
    articulo = re.sub(
        r"<[^>]+>", "", str(datos.get("articulo") or "")
    ).strip()

    if len(articulo) < 200:
        return None

    titulo = limpiar_html(str(datos.get("titulo") or pendiente["title"]))
    resumen = limpiar_html(str(datos.get("resumen") or ""))

    if not resumen:
        resumen = limpiar_html(articulo)[:200] + "..."

    categoria = str(datos.get("categoria") or pendiente.get("category", "Mundo")).strip()
    if categoria not in CATEGORIAS_VALIDAS:
        categoria = pendiente.get("category", "Mundo")

    fecha = convertir_fecha(pendiente.get("publishedAt"))
    if not fecha:
        fecha = datetime.now(UTC)

    return {
        "id": pendiente["id"],
        "title": titulo[:300],
        "summary": resumen[:300],
        "content": articulo,
        "source": pendiente.get("source", "Fuente RSS"),
        "sourceUrl": pendiente["sourceUrl"],
        "date": fecha.astimezone(ZONA_AR).strftime("%Y-%m-%d"),
        "publishedAt": fecha.isoformat(),
        "category": categoria,
        "imageUrl": pendiente.get("imageUrl") or IMAGEN_POR_DEFECTO,
    }


def ejecutar():
    ahora = datetime.now(UTC)
    limite = ahora - timedelta(hours=HORAS_MAXIMAS)

    print(f"IA configurada: {MODELO_IA}" if model else "Gemini no configurado; se conservarán pendientes.")

    anteriores = cargar_noticias()
    pendientes = cargar_pendientes()

    noticias = []
    urls = set()
    titulos = set()
    ids = set()

    # Conservar noticias actuales y construir índices de duplicados.
    for noticia in anteriores:
        if not isinstance(noticia, dict) or es_noticia_demo(noticia):
            continue

        fecha = convertir_fecha(noticia.get("publishedAt") or noticia.get("date"))
        if not fecha or fecha < limite or fecha > ahora + timedelta(minutes=5):
            continue

        enlace = str(noticia.get("sourceUrl") or "").strip()
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

    # Las pendientes se procesan primero cuando vuelve la cuota.
    cola_nueva = []
    procesadas_pendientes = 0

    for pendiente in pendientes:
        if not isinstance(pendiente, dict):
            continue

        enlace = str(pendiente.get("sourceUrl") or "").strip()
        if not enlace or enlace in urls:
            continue

        if (
            model is None
            or estado_ia["cuota_agotada"]
            or estado_ia["llamadas"] >= MAX_IA_POR_EJECUCION
        ):
            cola_nueva.append(pendiente)
            continue

        texto_base = str(pendiente.get("rawText") or "")
        if not texto_util(texto_base):
            cola_nueva.append(pendiente)
            continue

        datos = redactar_con_ia(pendiente["title"], texto_base)

        if datos:
            noticia = preparar_noticia(datos, pendiente)
            if noticia:
                noticias.append(noticia)
                urls.add(enlace)
                titulos.add(noticia["title"].casefold())
                ids.add(noticia["id"])
                procesadas_pendientes += 1
                continue

        cola_nueva.append(pendiente)

        if estado_ia["cuota_agotada"]:
            break

    # Añadir a la cola los pendientes que quedaron sin recorrer.
    if estado_ia["cuota_agotada"] or estado_ia["llamadas"] >= MAX_IA_POR_EJECUCION:
        ya_en_cola = {p.get("sourceUrl") for p in cola_nueva if isinstance(p, dict)}
        for pendiente in pendientes:
            if isinstance(pendiente, dict) and pendiente.get("sourceUrl") not in ya_en_cola:
                if pendiente.get("sourceUrl") not in urls:
                    cola_nueva.append(pendiente)
                    ya_en_cola.add(pendiente.get("sourceUrl"))

    nuevas = 0
    omitidas = 0

    # Leer RSS y encolar nuevas noticias para redacción con IA.
    for feed_url, categoria in RSS_FEEDS:
        try:
            feed = feedparser.parse(
                feed_url,
                request_headers={"User-Agent": "NoticiasGlobales/1.0"},
            )
        except Exception as error:
            print(f"Error leyendo RSS {feed_url}: {error}")
            continue

        if not feed.entries:
            print(f"RSS sin entradas: {feed_url}")
            continue

        vistas_en_fuente = 0

        for entry in feed.entries:
            if vistas_en_fuente >= POR_FUENTE:
                break

            titulo = limpiar_html(entry.get("title", ""))
            enlace = str(entry.get("link") or "").strip()
            resumen_rss = limpiar_html(
                entry.get("summary", "") or entry.get("description", "")
            )
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

            texto_crudo = obtener_contenido_completo(enlace) or resumen_rss
            if not texto_util(texto_crudo):
                print(f"Texto insuficiente; se omite por ahora: {titulo[:80]}")
                continue

            pendiente = {
                "id": identificador,
                "title": titulo,
                "source": limpiar_html(feed.feed.get("title", "Fuente RSS"))[:100],
                "sourceUrl": enlace,
                "publishedAt": fecha.isoformat(),
                "category": categoria,
                "imageUrl": imagen_de_entrada(entry),
                "rawText": texto_crudo[:18000],
            }

            datos = None
            if (
                model is not None
                and not estado_ia["cuota_agotada"]
                and estado_ia["llamadas"] < MAX_IA_POR_EJECUCION
            ):
                datos = redactar_con_ia(titulo, texto_crudo)

            if datos:
                noticia = preparar_noticia(datos, pendiente)
                if noticia:
                    noticias.append(noticia)
                    urls.add(enlace)
                    titulos.add(noticia["title"].casefold())
                    ids.add(identificador)
                    nuevas += 1
                    vistas_en_fuente += 1
                    continue

            # Si Gemini no pudo redactar, conservar en cola, nunca publicar
            # el texto RSS como si fuera un artículo original.
            cola_nueva.append(pendiente)
            urls.add(enlace)
            titulos.add(titulo.casefold())
            ids.add(identificador)
            omitidas += 1

            if estado_ia["cuota_agotada"] or estado_ia["llamadas"] >= MAX_IA_POR_EJECUCION:
                break

        if estado_ia["cuota_agotada"] or estado_ia["llamadas"] >= MAX_IA_POR_EJECUCION:
            print("Pausa de IA: el resto se intentará en ejecuciones futuras.")
            # No recorrer más fuentes si no quedan llamadas disponibles.
            break

    # Quitar duplicados de la cola por URL.
    pendientes_unicos = []
    enlaces_pendientes = set()
    for pendiente in cola_nueva:
        if not isinstance(pendiente, dict):
            continue
        enlace = pendiente.get("sourceUrl")
        if enlace and enlace not in urls and enlace not in enlaces_pendientes:
            pendientes_unicos.append(pendiente)
            enlaces_pendientes.add(enlace)

    noticias.sort(
        key=lambda noticia: noticia.get("publishedAt", ""),
        reverse=True,
    )

    guardar_noticias(noticias[:MAX_NOTICIAS])
    guardar_pendientes(pendientes_unicos)

    print(
        f"Proceso terminado: {nuevas} noticias nuevas; "
        f"{procesadas_pendientes} pendientes procesadas; "
        f"{len(pendientes_unicos)} en cola; "
        f"{min(len(noticias), MAX_NOTICIAS)} publicadas; "
        f"{estado_ia['llamadas']} llamadas a Gemini."
    )


if __name__ == "__main__":
    ejecutar()
