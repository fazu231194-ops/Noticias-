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
import requests
import trafilatura
import google.generativeai as genai

# ============================================================
# CONFIGURACION
# ============================================================

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
MODELO_IA = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

if API_KEY:
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODELO_IA)
else:
    model = None

NEWS_FILE_PATH = "src/data/news.json"
PENDING_FILE_PATH = "src/data/pending_news.json"

MAX_NOTICIAS = 300
POR_FUENTE = 2
HORAS_MAXIMAS = 168  # Conserva noticias y pendientes de hasta 7 dias
MIN_TEXTO_BASE = 200
MIN_PALABRAS_ARTICULO = 450
MAX_TEXTO_POR_NOTA = 6000

# Maximo 3 llamadas "productivas" por ejecucion.
# Con 4 ejecuciones diarias: hasta 12 solicitudes por dia (cupo gratuito: 20/dia).
NOTAS_POR_LLAMADA = 2
MAX_LLAMADAS_POR_EJECUCION = 3
PAUSA_ENTRE_LLAMADAS = 20
PAUSA_LIMITE_MINUTO = 65
MAX_FALLOS_SEGUIDOS = 2
MAX_INTENTOS_NOTA = 3
MAX_COLA = 30
MAX_CANDIDATAS_NUEVAS = 16

# Limites de tiempo de las descargas.
TIMEOUT_CONEXION = 5
TIMEOUT_RSS = 10
TIMEOUT_ARTICULO = 12
TIMEOUT_GEMINI = 90

estado_ia = {
    "llamadas": 0,
    "fallos_seguidos": 0,
    "cuota_agotada": False,
}

UTC = timezone.utc
ZONA_AR = timezone(timedelta(hours=-3))

IMAGEN_POR_DEFECTO = (
    "https://images.unsplash.com/photo-1504711434969-e33886168f5c"
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

PROMPT = """Sos periodista y editor de Panorama Global News.
Recibís __CANTIDAD__ notas de origen. Para CADA una, redactá una nota
periodística original en español, clara y útil para el lector.

REGLAS OBLIGATORIAS:
- Objetivo: entre 500 y 800 palabras por artículo. Priorizá el desarrollo
  del tema por sobre la extensión exacta.
- No rellenes ni repitas ideas para alcanzar la extensión. Si la fuente no
  tiene suficiente información, desarrollá todo el contexto disponible
  (antecedentes del tema, implicancias, datos conexos presentes en la
  fuente) antes que inventar hechos.
- Usá únicamente hechos, cifras, nombres, fechas y declaraciones presentes
  en el texto base. No agregues antecedentes externos ni supongas consecuencias.
- No inventes citas, fuentes, declaraciones, cifras ni detalles.
- Redactá con estructura propia; no copies párrafos de la fuente ni reproduzcas
  más de 6 palabras seguidas del texto base.
- Separá los hechos confirmados de las posibilidades.
- Si no hay una noticia real o información suficiente y fiable, dejá "articulo" vacío.
- Tratá cada nota por separado. No mezcles datos entre notas.
- Texto plano, con párrafos separados por una línea en blanco. Sin markdown,
  asteriscos, numerales ni viñetas. Ignorá menús, publicidad y enlaces relacionados.
- Empezá por el hecho principal, desarrollá los detalles disponibles y cerrá
  con un párrafo informativo sin inventar conclusiones.

Elegí "categoria" entre: Mundo, Sociedad, Economía, Tecnología, Deportes, Ciencia.

Devolvé SOLO JSON válido:
{"notas":[{"indice":1,"titulo":"título en español, máximo 120 caracteres",
"resumen":"1 o 2 oraciones, máximo 200 caracteres","categoria":"categoría válida",
"articulo":"nota completa en texto plano"}]}
Incluí una entrada por nota con el mismo número de indice.

__NOTAS__
"""


# ============================================================
# LIMPIEZA Y FECHAS
# ============================================================

def limpiar_html(texto):
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", html.unescape(texto)).strip()


def limpiar_texto_articulo(texto):
    texto = re.sub(r"<[^>]+>", "", str(texto or ""))
    texto = texto.replace("**", "").replace("__", "")
    texto = re.sub(r"(?m)^\s*#+\s*", "", texto)
    texto = re.sub(r"(?m)^\s*[-*•]\s+", "", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


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


# ============================================================
# DESCARGAS CON TIEMPO LIMITE
# ============================================================

def obtener_contenido_completo(url):
    """Descarga una página con timeout y extrae su texto principal."""
    try:
        respuesta = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; PanoramaGlobalNews/1.0)"
                )
            },
            timeout=(TIMEOUT_CONEXION, TIMEOUT_ARTICULO),
        )
        respuesta.raise_for_status()

        texto = trafilatura.extract(respuesta.text)

        if texto and len(texto) > MIN_TEXTO_BASE:
            return texto

    except requests.RequestException as error:
        print(f"Error/timeout descargando artículo {url}: {error}")
    except Exception as error:
        print(f"Error extrayendo artículo {url}: {error}")

    return None


def texto_util(texto):
    return bool(
        texto
        and len(texto.strip()) >= MIN_TEXTO_BASE
        and not texto.strip().startswith("Watch CBS News")
    )


# ============================================================
# GEMINI
# ============================================================

def es_error_cuota_minuto(error):
    mensaje = str(error).lower()
    return "per minute" in mensaje or "requestsperminute" in mensaje


def es_error_cuota_dia(error):
    mensaje = str(error).lower()
    return "per day" in mensaje or "requestsperday" in mensaje


def es_error_cuota(error):
    mensaje = str(error).lower()
    return any(
        palabra in mensaje
        for palabra in ("429", "quota", "rate limit", "resource_exhausted", "too many requests")
    )


def es_bloqueo(error):
    mensaje = str(error).lower()
    return any(
        palabra in mensaje
        for palabra in ("block_reason", "prohibited_content", "prompt_feedback")
    )


def construir_prompt(lote):
    bloques = []

    for i, pendiente in enumerate(lote, start=1):
        texto = str(pendiente.get("rawText") or "")[:MAX_TEXTO_POR_NOTA]

        bloques.append(
            f"=== NOTA {i} ===\n"
            f"TÍTULO ORIGINAL: {pendiente.get('title', '')}\n"
            f"TEXTO BASE:\n{texto}"
        )

    return (
        PROMPT.replace("__CANTIDAD__", str(len(lote)))
        .replace("__NOTAS__", "\n\n".join(bloques))
    )


def pedir_a_gemini(lote):
    """Devuelve (lista_de_notas, estado).
    estado: 'ok', 'quota_dia', 'bloqueado', 'error_temporal'."""

    if model is None or estado_ia["cuota_agotada"]:
        return None, "cuota_dia"

    if estado_ia["llamadas"] >= MAX_LLAMADAS_POR_EJECUCION:
        print("Límite de llamadas a Gemini alcanzado en esta ejecución.")
        return None, "error_temporal"

    # Hasta 2 intentos: si el primero choca con el límite por minuto,
    # esperamos y reintentamos una vez antes de darnos por vencidos.
    for intento in (1, 2):
        if estado_ia["llamadas"] > 0:
            time.sleep(PAUSA_ENTRE_LLAMADAS)

        estado_ia["llamadas"] += 1

        try:
            respuesta = model.generate_content(
                construir_prompt(lote),
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.4,
                    "max_output_tokens": 16384,
                },
                request_options={"timeout": TIMEOUT_GEMINI},
            )

            texto = (respuesta.text or "").strip() if respuesta else ""
            texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)

            if not texto:
                raise ValueError("Gemini devolvió una respuesta vacía.")

            datos = json.loads(texto)
            notas = datos.get("notas") if isinstance(datos, dict) else datos

            if not isinstance(notas, list):
                raise ValueError("La respuesta no contiene una lista de notas.")

            estado_ia["fallos_seguidos"] = 0
            return notas, "ok"

        except Exception as error:
            print(f"Error IA (intento {intento}/2): {error}")

            if es_bloqueo(error):
                print("Gemini bloqueó este lote por contenido sensible.")
                return None, "bloqueado"

            if es_error_cuota_dia(error):
                estado_ia["cuota_agotada"] = True
                print("Cuota DIARIA agotada. Lo que falta queda en la cola.")
                return None, "quota_dia"

            if es_error_cuota_minuto(error) or es_error_cuota(error):
                if intento == 1:
                    print(f"Límite por minuto. Espero {PAUSA_LIMITE_MINUTO}s y reintento.")
                    time.sleep(PAUSA_LIMITE_MINUTO)
