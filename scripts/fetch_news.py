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
MIN_PALABRAS_ARTICULO = 300
MAX_TEXTO_POR_NOTA = 6000

# Límites del plan gratuito: 20 solicitudes por día y 5 por minuto
NOTAS_POR_LLAMADA = 3
MAX_LLAMADAS_POR_EJECUCION = 4
PAUSA_ENTRE_LLAMADAS = 15  # segundos
MAX_FALLOS_SEGUIDOS = 2
MAX_INTENTOS_NOTA = 4
MAX_COLA = 30
MAX_CANDIDATAS_NUEVAS = 20

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

PROMPT = """Sos periodista y editor de Noticias Globales.

Recibís __CANTIDAD__ notas de origen. Para CADA una, escribí una nota
periodística ORIGINAL en español, con estructura y redacción propias.

REGLAS:
- No cambies solo palabras por sinónimos. No repitas más de 6 palabras
  seguidas del texto base.
- Usá únicamente datos que estén en el texto base. No inventes cifras,
  nombres, declaraciones ni antecedentes.
- Distinguí los hechos confirmados de las posibilidades o interpretaciones.
- Extensión: entre 350 y 600 palabras por nota, según la información
  disponible. Si la fuente es escasa, escribí una nota más corta pero
  completa. No rellenes ni repitas ideas.
- Texto plano: párrafos separados por una línea en blanco. Sin markdown,
  sin asteriscos, sin numerales y sin viñetas.
- Ignorá menús, publicidad, enlaces a otras notas, "minutos de lectura" y
  textos de videos.
- Si el texto base de una nota no contiene una noticia real, dejá el campo
  "articulo" de esa nota vacío.
- Tratá cada nota de forma independiente. No mezcles datos entre notas.

Elegí "categoria" entre: Mundo, Sociedad, Economía, Tecnología, Deportes, Ciencia.

Devolvé SOLO un JSON válido con esta forma:
{"notas": [
  {"indice": 1,
   "titulo": "título en español, máximo 120 caracteres",
   "resumen": "1 o 2 oraciones, máximo 200 caracteres",
   "categoria": "una categoría válida",
   "articulo": "la nota completa en texto plano"}
]}
Incluí una entrada por cada nota, con el mismo número de "indice".

__NOTAS__
"""


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


def obtener_contenido_completo(url):
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
    """Envía un lote de notas a Gemini. Devuelve una lista de notas o None."""
    if model is None or estado_ia["cuota_agotada"]:
        return None

    prompt = construir_prompt(lote)

    for intento in (1, 2):
        if estado_ia["llamadas"] >= MAX_LLAMADAS_POR_EJECUCION:
            print("Límite de llamadas a Gemini alcanzado en esta ejecución.")
            return None

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
            notas = datos.get("notas") if isinstance(datos, dict) else datos

            if not isinstance(notas, list):
                raise ValueError("La respuesta no contiene una lista de notas.")

            estado_ia["fallos_seguidos"] = 0
            return notas

        except Exception as error:
            print(f"Error IA (intento {intento}/2): {error}")

            if es_error_cuota(error):
                if intento == 1:
                    print("Límite alcanzado. Espero 65 segundos y reintento una vez.")
                    time.sleep(65)
                    continue
                estado_ia["cuota_agotada"] = True
                print("Cuota de Gemini agotada. Lo que falta queda en la cola.")
                return None

            break

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
    if len(articulo.split()) < MIN_PALABRAS_ARTICULO:
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


def ejecutar():
    ahora = datetime.now(UTC)
    limite = ahora - timedelta(hours=HORAS_MAXIMAS)

    if model:
        print(f"IA configurada: {MODELO_IA}")
    else:
        print("ATENCIÓN: no hay clave de Gemini; solo se actualiza la cola.")

    anteriores = cargar_json(NEWS_FILE_PATH, [])
    if not isinstance(anteriores, list):
        anteriores = []

    pendientes = cargar_json(PENDING_FILE_PATH, [])
    if not isinstance(pendientes, list):
        pendientes = []

    # 1. Noticias ya publicadas (se conservan las de las últimas 48 horas)
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

        if (enlace and enlace in urls_publicadas) or (
            titulo and titulo in titulos_publicados
        ):
            continue

        noticias.append(noticia)
        if enlace:
            urls_publicadas.add(enlace)
        if titulo:
            titulos_publicados.add(titulo)
        if noticia.get("id"):
            ids_publicados.add(str(noticia["id"]))

    # 2. Cola de pendientes de corridas anteriores
    cola = []
    urls_en_cola = set()
    titulos_en_cola = set()

    for pendiente in pendientes:
        if not isinstance(pendiente, dict):
            continue

        enlace = str(pendiente.get("sourceUrl") or "").strip()
        fecha = convertir_fecha(pendiente.get("publishedAt"))

        if not enlace or not fecha or fecha < limite:
            continue
        if enlace in urls_publicadas or enlace in urls_en_cola:
            continue
        if not texto_util(str(pendiente.get("rawText") or "")):
            continue

        cola.append(pendiente)
        urls_en_cola.add(enlace)
        titulos_en_cola.add(limpiar_html(pendiente.get("title", "")).casefold())

    # 3. Buscar noticias nuevas en los RSS (se rota la fuente inicial)
    inicio = (ahora.hour // 6 * 5) % len(RSS_FEEDS)
    feeds = RSS_FEEDS[inicio:] + RSS_FEEDS[:inicio]
    candidatas_nuevas = 0

    for feed_url, categoria in feeds:
        if len(cola) >= MAX_COLA or candidatas_nuevas >= MAX_CANDIDATAS_NUEVAS:
            break

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

        vistas = 0

        for entry in feed.entries:
            if vistas >= POR_FUENTE:
                break
            if len(cola) >= MAX_COLA or candidatas_nuevas >= MAX_CANDIDATAS_NUEVAS:
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
            if enlace in urls_publicadas or enlace in urls_en_cola:
                continue
            if titulo.casefold() in titulos_publicados:
                continue
            if titulo.casefold() in titulos_en_cola:
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

    # 4. Redactar la cola en lotes, empezando por lo más reciente
    cola.sort(key=lambda p: p.get("publishedAt", ""), reverse=True)

    cola_restante = []
    publicadas_ahora = 0
    posicion = 0

    while posicion < len(cola):
        puede_llamar = (
            model is not None
            and not estado_ia["cuota_agotada"]
            and estado_ia["llamadas"] < MAX_LLAMADAS_POR_EJECUCION
            and estado_ia["fallos_seguidos"] < MAX_FALLOS_SEGUIDOS
        )

        if not puede_llamar:
            cola_restante.extend(cola[posicion:])
            break

        lote = cola[posicion:posicion + NOTAS_POR_LLAMADA]
        posicion += NOTAS_POR_LLAMADA

        notas = pedir_a_gemini(lote)

        resultados = {}
        for nota in notas or []:
            if isinstance(nota, dict):
                try:
                    resultados[int(nota.get("indice"))] = nota
                except (TypeError, ValueError):
                    pass

        for i, pendiente in enumerate(lote, start=1):
            noticia = preparar_noticia(resultados.get(i), pendiente)

            if noticia:
                noticias.append(noticia)
                urls_publicadas.add(pendiente["sourceUrl"])
                titulos_publicados.add(noticia["title"].casefold())
                ids_publicados.add(str(noticia["id"]))
                publicadas_ahora += 1
                continue

            if not estado_ia["cuota_agotada"]:
                pendiente["intentos"] = int(pendiente.get("intentos", 0)) + 1
                if pendiente["intentos"] >= MAX_INTENTOS_NOTA:
                    print(f"Se descarta tras varios intentos: {pendiente['title'][:80]}")
                    continue

            cola_restante.append(pendiente)

    # 5. Guardar resultados
    cola_restante = [
        p for p in cola_restante if p.get("sourceUrl") not in urls_publicadas
    ][:MAX_COLA]

    noticias.sort(key=lambda n: n.get("publishedAt", ""), reverse=True)

    guardar_json(NEWS_FILE_PATH, noticias[:MAX_NOTICIAS])
    guardar_json(PENDING_FILE_PATH, cola_restante)

    print(
        f"Proceso terminado: {publicadas_ahora} noticias nuevas; "
        f"{len(cola_restante)} en cola; "
        f"{min(len(noticias), MAX_NOTICIAS)} publicadas; "
        f"{estado_ia['llamadas']} llamadas a Gemini"
        + ("; cuota agotada." if estado_ia["cuota_agotada"] else ".")
    )


if __name__ == "__main__":
    ejecutar()
