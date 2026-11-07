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
from groq import Groq

# ============================================================
# CONFIGURACION DE LAS DOS IA (GEMINI PRIMERO, GROQ DE RESPALDO)
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
MODELO_GEMINI = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel(MODELO_GEMINI)
else:
    gemini_model = None

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
MODELO_GROQ = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

if GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY, timeout=60.0)
else:
    groq_client = None

NEWS_FILE_PATH = "src/data/news.json"
PENDING_FILE_PATH = "src/data/pending_news.json"

MAX_NOTICIAS = 300
POR_FUENTE = 2
HORAS_MAXIMAS = 168
MIN_TEXTO_BASE = 200
MIN_PALABRAS_ARTICULO = 450
MAX_TEXTO_POR_NOTA = 4000

NOTAS_POR_LLAMADA = 1

MAX_LLAMADAS_GEMINI = 4
PAUSA_GEMINI = 20
PAUSA_LIMITE_MINUTO_GEMINI = 65

MAX_LLAMADAS_GROQ = 20
PAUSA_GROQ = 4

MAX_FALLOS_SEGUIDOS = 3
MAX_INTENTOS_NOTA = 3
MAX_COLA = 30
MAX_CANDIDATAS_NUEVAS = 16

TIMEOUT_CONEXION = 5
TIMEOUT_RSS = 10
TIMEOUT_ARTICULO = 12
TIMEOUT_GEMINI = 120

estado_gemini = {"llamadas": 0, "cuota_agotada": False}
estado_groq = {"llamadas": 0, "cuota_agotada": False}
fallos_seguidos = 0

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

CATEGORIAS_VALIDAS = {"Mundo", "Sociedad", "Economía", "Tecnología", "Deportes", "Ciencia"}

FUENTES_DEMO = {
    "techdaily", "webnews global", "economía hoy", "planeta urbano", "deportes total",
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
  antes que inventar hechos.
- Usá únicamente hechos, cifras, nombres, fechas y declaraciones presentes
  en el texto base. No agregues antecedentes externos ni supongas consecuencias.
- No inventes citas, fuentes, declaraciones, cifras ni detalles.
- Redactá con estructura propia; no copies párrafos de la fuente ni reproduzcas
  más de 6 palabras seguidas del texto base.
- Si no hay una noticia real o información suficiente, dejá "articulo" vacío.
- Texto plano, con párrafos separados por una línea en blanco. Sin markdown,
  asteriscos, numerales ni viñetas. Ignorá menús, publicidad y enlaces relacionados.

Elegí "categoria" entre: Mundo, Sociedad, Economía, Tecnología, Deportes, Ciencia.

Devolvé SOLO JSON válido, sin texto antes ni después:
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
    for grupo in (entry.get("media_content", []), entry.get("media_thumbnail", [])):
        for media in grupo:
            if media.get("url"):
                return media["url"]
    for enclosure in entry.get("enclosures", []):
        if enclosure.get("type", "").startswith("image") and enclosure.get("href"):
            return enclosure["href"]
    return IMAGEN_POR_DEFECTO


# ============================================================
# DESCARGAS CON TIEMPO LIMITE
# ============================================================

def obtener_contenido_completo(url):
    try:
        respuesta = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; PanoramaGlobalNews/1.0)"},
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
# AYUDANTES PARA LEER ERRORES DE LAS IA
# ============================================================

def es_error_cuota_minuto(error):
    mensaje = str(error).lower()
    return "per minute" in mensaje or "requestsperminute" in mensaje


def es_error_cuota_dia(error):
    mensaje = str(error).lower()
    return "per day" in mensaje or "requestsperday" in mensaje


def es_error_cuota(error):
    mensaje = str(error).lower()
    return any(p in mensaje for p in ("429", "quota", "rate limit", "resource_exhausted", "too many requests"))


def es_bloqueo(error):
    mensaje = str(error).lower()
    return any(p in mensaje for p in ("block_reason", "prohibited_content", "prompt_feedback", "content_filter"))


def extraer_json_notas(texto):
    texto = (texto or "").strip()
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)
    if not texto:
        raise ValueError("Respuesta vacía.")
    datos = json.loads(texto)
    notas = datos.get("notas") if isinstance(datos, dict) else datos
    if not isinstance(notas, list):
        raise ValueError("La respuesta no contiene una lista de notas.")
    return notas


def construir_prompt(lote):
    bloques = []
    for i, pendiente in enumerate(lote, start=1):
        texto = str(pendiente.get("rawText") or "")[:MAX_TEXTO_POR_NOTA]
        bloques.append(f"=== NOTA {i} ===\nTÍTULO ORIGINAL: {pendiente.get('title', '')}\nTEXTO BASE:\n{texto}")
    return PROMPT.replace("__CANTIDAD__", str(len(lote))).replace("__NOTAS__", "\n\n".join(bloques))


# ============================================================
# GEMINI
# ============================================================

def pedir_a_gemini(lote):
    """Devuelve (notas, estado): 'ok' | 'quota_dia' | 'bloqueado' | 'error_temporal'."""
    if gemini_model is None or estado_gemini["cuota_agotada"]:
        return None, "quota_dia"

    if estado_gemini["llamadas"] >= MAX_LLAMADAS_GEMINI:
        return None, "error_temporal"

    prompt = construir_prompt(lote)

    for intento in (1, 2):
        if estado_gemini["llamadas"] > 0:
            time.sleep(PAUSA_GEMINI)
        estado_gemini["llamadas"] += 1

        try:
            respuesta = gemini_model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.4,
                    "max_output_tokens": 8192,
                },
                request_options={"timeout": TIMEOUT_GEMINI},
            )
            texto = (respuesta.text or "").strip() if respuesta else ""
            notas = extraer_json_notas(texto)
            return notas, "ok"

        except Exception as error:
            print(f"Error Gemini (intento {intento}/2): {error}")

            if es_bloqueo(error):
                print("Gemini bloqueó este lote por contenido sensible.")
                return None, "bloqueado"

            if es_error_cuota_dia(error):
                estado_gemini["cuota_agotada"] = True
                print("Cuota DIARIA de Gemini agotada. Se prueba con Groq.")
                return None, "quota_dia"

            if es_error_cuota_minuto(error) or es_error_cuota(error):
                if intento == 1:
                    print(f"Límite por minuto en Gemini. Espero {PAUSA_LIMITE_MINUTO_GEMINI}s y reintento.")
                    time.sleep(PAUSA_LIMITE_MINUTO_GEMINI)
                    continue
                return None, "error_temporal"

            # Timeout u otro error puntual de Gemini.
            return None, "error_temporal"

    return None, "error_temporal"


# ============================================================
# GROQ (RESPALDO)
# ============================================================

def pedir_a_groq(lote):
    """Devuelve (notas, estado): 'ok' | 'quota_dia' | 'bloqueado' | 'error_temporal'."""
    if groq_client is None or estado_groq["cuota_agotada"]:
        return None, "error_temporal"

    if estado_groq["llamadas"] >= MAX_LLAMADAS_GROQ:
        return None, "error_temporal"

    if estado_groq["llamadas"] > 0:
        time.sleep(PAUSA_GROQ)
    estado_groq["llamadas"] += 1

    prompt = construir_prompt(lote)

    try:
        respuesta = groq_client.chat.completions.create(
            model=MODELO_GROQ,
            messages=[
                {"role": "system", "content": "Respondés siempre con JSON válido, sin texto adicional."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
            max_tokens=8192,
        )
        texto = respuesta.choices[0].message.content if respuesta and respuesta.choices else ""
        notas = extraer_json_notas(texto)
        return notas, "ok"

    except Exception as error:
        print(f"Error Groq: {error}")

        if es_bloqueo(error):
            print("Groq bloqueó este lote por contenido sensible.")
            return None, "bloqueado"

        if es_error_cuota_dia(error):
            estado_groq["cuota_agotada"] = True
            print("Cuota DIARIA de Groq agotada.")
            return None, "quota_dia"

        # Límite por minuto, timeout, modelo inválido, etc.: se reintenta en otra ejecución.
        return None, "error_temporal"


# ============================================================
# ORQUESTADOR: GEMINI PRIMERO, GROQ DE RESPALDO
# ============================================================

def pedir_redaccion(lote):
    """Intenta Gemini; si no puede, prueba Groq. Devuelve (notas, estado)."""
    notas, estado = pedir_a_gemini(lote)

    if estado == "ok" or estado == "bloqueado":
        return notas, estado

    # Gemini no pudo (cuota diaria, límite de la ejecución, o error puntual): probamos Groq.
    notas, estado_groq_resultado = pedir_a_groq(lote)
    return notas, estado_groq_resultado


# ============================================================
# ARCHIVOS JSON
# ============================================================

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


# ============================================================
# VALIDACION DE NOTICIAS
# ============================================================

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
    if not isinstance(datos, dict):
        return None
    articulo = limpiar_texto_articulo(datos.get("articulo"))
    palabras = len(articulo.split())
    if palabras < MIN_PALABRAS_ARTICULO:
        print(f"Artículo muy corto ({palabras} palabras): {pendiente.get('title', '')[:80]}")
        return None
    titulo = limpiar_html(str(datos.get("titulo") or "")) or pendiente["title"]
    resumen = limpiar_html(str(datos.get("resumen") or ""))
    if not resumen:
        resumen = limpiar_html(articulo)[:200] + "..."
    categoria = str(datos.get("categoria") or "").strip()
    if categoria not in CATEGORIAS_VALIDAS:
        categoria = pendiente.get("category", "Mundo")
    if categoria not in CATEGORIAS_VALIDAS:
        categoria = "Mundo"
    fecha = convertir_fecha(pendiente.get("publishedAt")) or datetime.now(UTC)
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


# ============================================================
# PROCESO PRINCIPAL
# ============================================================

def ejecutar():
    global fallos_seguidos
    ahora = datetime.now(UTC)
    limite = ahora - timedelta(hours=HORAS_MAXIMAS)

    if gemini_model:
        print(f"Gemini configurado: {MODELO_GEMINI}")
    else:
        print("ATENCIÓN: no hay clave de Gemini.")

    if groq_client:
        print(f"Groq configurado como respaldo: {MODELO_GROQ}")
    else:
        print("ATENCIÓN: no hay clave de Groq; no habrá respaldo si Gemini falla.")

    anteriores = cargar_json(NEWS_FILE_PATH, [])
    if not isinstance(anteriores, list):
        anteriores = []
    pendientes = cargar_json(PENDING_FILE_PATH, [])
    if not isinstance(pendientes, list):
        pendientes = []

    noticias = []
    urls_publicadas = set()
    titulos_publicados = set()
    ids_publicados = set()

    for noticia in anteriores:
        if not isinstance(noticia, dict) or es_noticia_demo(noticia):
            continue
        fecha = convertir_fecha(noticia.get("publishedAt") or noticia.get("date"))
        if not fecha or fecha < limite or fecha > ahora + timedelta(minutes=5):
            continue
        enlace = str(noticia.get("sourceUrl") or "").strip()
        titulo = limpiar_html(noticia.get("title", "")).casefold()
        if (enlace and enlace in urls_publicadas) or (titulo and titulo in titulos_publicados):
            continue
        noticias.append(noticia)
        if enlace:
            urls_publicadas.add(enlace)
        if titulo:
            titulos_publicados.add(titulo)
        if noticia.get("id"):
            ids_publicados.add(str(noticia["id"]))

    cola = []
    urls_en_cola = set()
    titulos_en_cola = set()

    for pendiente in pendientes:
        if not isinstance(pendiente, dict):
            continue
        enlace = str(pendiente.get("sourceUrl") or "").strip()
        fecha = convertir_fecha(pendiente.get("publishedAt"))
        if not enlace or not fecha or fecha < limite or fecha > ahora + timedelta(minutes=5):
            continue
        if enlace in urls_publicadas or enlace in urls_en_cola:
            continue
        if not texto_util(str(pendiente.get("rawText") or "")):
            continue
        cola.append(pendiente)
        urls_en_cola.add(enlace)
        titulos_en_cola.add(limpiar_html(pendiente.get("title", "")).casefold())

    inicio = (ahora.hour // 6 * 5) % len(RSS_FEEDS)
    feeds = RSS_FEEDS[inicio:] + RSS_FEEDS[:inicio]
    candidatas_nuevas = 0

    for feed_url, categoria in feeds:
        if len(cola) >= MAX_COLA or candidatas_nuevas >= MAX_CANDIDATAS_NUEVAS:
            break
        try:
            respuesta = requests.get(
                feed_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; PanoramaGlobalNews/1.0)"},
                timeout=(TIMEOUT_CONEXION, TIMEOUT_RSS),
            )
            respuesta.raise_for_status()
            feed = feedparser.parse(respuesta.content)
        except requests.RequestException as error:
            print(f"Error/timeout RSS {feed_url}: {error}")
            continue
        except Exception as error:
            print(f"Error leyendo RSS {feed_url}: {error}")
            continue

        if not feed.entries:
            print(f"RSS sin entradas: {feed_url}")
            continue

        vistas = 0
        for entry in feed.entries:
            if vistas >= POR_FUENTE:
                break
            if len(cola) >= MAX_COLA or candidatas_nuevas >= MAX_CANDIDATAS_NUEVAS:
                break

            titulo = limpiar_html(entry.get("title", ""))
            enlace = str(entry.get("link") or "").strip()
            resumen_rss = limpiar_html(entry.get("summary", "") or entry.get("description", ""))
            fecha = fecha_publicacion(entry)

            if not titulo or not enlace or not fecha:
                continue
            if fecha < limite or fecha > ahora + timedelta(minutes=5):
                continue
            if enlace in urls_publicadas or enlace in urls_en_cola:
                continue
            if titulo.casefold() in titulos_publicados or titulo.casefold() in titulos_en_cola:
                continue

            identificador = hashlib.sha1(enlace.encode("utf-8")).hexdigest()[:16]
            if identificador in ids_publicados:
                continue

            texto_crudo = obtener_contenido_completo(enlace) or resumen_rss
            if not texto_util(texto_crudo):
                print(f"Texto insuficiente; se omite: {titulo[:80]}")
                continue

            cola.append({
                "id": identificador,
                "title": titulo,
                "source": limpiar_html(feed.feed.get("title", "Fuente RSS"))[:100],
                "sourceUrl": enlace,
                "publishedAt": fecha.isoformat(),
                "category": categoria,
                "imageUrl": imagen_de_entrada(entry),
                "rawText": texto_crudo[:MAX_TEXTO_POR_NOTA],
                "intentos": 0,
            })
            urls_en_cola.add(enlace)
            titulos_en_cola.add(titulo.casefold())
            vistas += 1
            candidatas_nuevas += 1

    cola.sort(key=lambda p: p.get("publishedAt", ""), reverse=True)

    cola_restante = []
    publicadas_ahora = 0
    posicion = 0

    while posicion < len(cola):
        gemini_disponible = (
            gemini_model is not None
            and not estado_gemini["cuota_agotada"]
            and estado_gemini["llamadas"] < MAX_LLAMADAS_GEMINI
        )
        groq_disponible = (
            groq_client is not None
            and not estado_groq["cuota_agotada"]
            and estado_groq["llamadas"] < MAX_LLAMADAS_GROQ
        )

        if (not gemini_disponible and not groq_disponible) or fallos_seguidos >= MAX_FALLOS_SEGUIDOS:
            cola_restante.extend(cola[posicion:])
            break

        if cola[posicion].get("solo"):
            lote = [cola[posicion]]
        else:
            lote = []
            for candidata in cola[posicion:posicion + NOTAS_POR_LLAMADA]:
                if candidata.get("solo"):
                    break
                lote.append(candidata)
        posicion += len(lote)

        notas, estado = pedir_redaccion(lote)

        if estado == "ok":
            fallos_seguidos = 0
        elif estado not in ("bloqueado",):
            fallos_seguidos += 1

        if estado == "quota_dia":
            # Ninguna de las dos IA pudo: el lote vuelve entero a la cola.
            cola_restante.extend(lote)
            continue

        resultados = {}
        for nota in notas or []:
            if isinstance(nota, dict):
                try:
                    resultados[int(nota.get("indice"))] = nota
                except (TypeError, ValueError):
                    pass

        for i, pendiente in enumerate(lote, start=1):
            if estado == "bloqueado":
                if len(lote) == 1:
                    print(f"Se descarta por contenido sensible: {pendiente['title'][:80]}")
                else:
                    pendiente["solo"] = True
                    cola_restante.append(pendiente)
                continue

            if estado == "error_temporal":
                cola_restante.append(pendiente)
                continue

            noticia = preparar_noticia(resultados.get(i), pendiente)
            if noticia:
                noticias.append(noticia)
                urls_publicadas.add(pendiente["sourceUrl"])
                titulos_publicados.add(noticia["title"].casefold())
                ids_publicados.add(str(noticia["id"]))
                publicadas_ahora += 1
                continue

            pendiente["intentos"] = int(pendiente.get("intentos", 0)) + 1
            if pendiente["intentos"] >= MAX_INTENTOS_NOTA:
                print(f"Se descarta tras varios intentos: {pendiente['title'][:80]}")
                continue
            cola_restante.append(pendiente)

    cola_restante = [p for p in cola_restante if p.get("sourceUrl") not in urls_publicadas][:MAX_COLA]
    noticias.sort(key=lambda n: n.get("publishedAt", ""), reverse=True)

    guardar_json(NEWS_FILE_PATH, noticias[:MAX_NOTICIAS])
    guardar_json(PENDING_FILE_PATH, cola_restante)

    print(
        f"Proceso terminado: {publicadas_ahora} noticias nuevas; "
        f"{len(cola_restante)} en cola; "
        f"{min(len(noticias), MAX_NOTICIAS)} publicadas; "
        f"Gemini: {estado_gemini['llamadas']} llamadas"
        + (" (cuota agotada)" if estado_gemini["cuota_agotada"] else "")
        + f"; Groq: {estado_groq['llamadas']} llamadas"
        + (" (cuota agotada)." if estado_groq["cuota_agotada"] else ".")
    )


if __name__ == "__main__":
    ejecutar()
