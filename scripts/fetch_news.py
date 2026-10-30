importar hashlib
importar html
importar json
importar sistema operativo
importar re
hora de importación
importar calendario
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

importar analizador de feeds
solicitudes de importación
importar trafilatura
importar google.generativeai como genai

# ============================================================
# CONFIGURACIÓN
# ============================================================

API_KEY = os.environ.get("GEMINI_API_KEY") o os.environ.get("GOOGLE_API_KEY")
MODELO_IA = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

si API_KEY:
    genai.configure(api_key=API_KEY)
    modelo = genai.GenerativeModel(MODELO_IA)
demás:
    modelo = Ninguno

RUTA_ARCHIVO_NOTICIAS = "src/data/news.json"
RUTA_ARCHIVO_PENDIENTE = "src/data/pending_news.json"

MÁXIMO_NOTICIAS = 300
POR_FUENTE = 2
HORAS_MAXIMAS = 168 # Conserva noticias y pendientes de hasta 7 días
BASE_TEXTO_MIN = 200
MIN_PALABRAS_ARTICULO = 700
MAX_TEXTO_POR_NOTA = 6000

# Maximo 4 llamadas por ejecucion.
# Con 4 ejecuciones diarias: hasta 16 solicitudes por día.
NOTAS_POR_LLAMADA = 2
MAX_LLAMADAS_POR_EJECUCION = 4
PAUSA_ENTRE_LLAMADAS = 20
MAX_FALLOS_SEGUIDOS = 2
MAX_INTENTOS_NOTA = 3
MAX_COLA = 30
MAX_CANDIDATAS_NUEVAS = 16

# Limites de tiempo de las descargas.
TIEMPO DE ESPERA_CONEXIÓN = 5
TIEMPO DE ESPERA_RSS = 10
TIMEOUT_ARTICULO = 12
TIEMPO DE ESPERA_GEMINI = 90

estado_ia = {
    "llamadas": 0,
    "fallos_seguidos": 0,
    "cuota_agotada": Falso,
}

UTC = zona horaria.utc
ZONA_AR = zona horaria(timedelta(horas=-3))

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

CATEGORÍAS_VÁLIDAS = {
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
Recibís __CANTIDAD__ notas de origen. Para CADA una, redactará una nota
periodística original en español, extensa, clara y útil para el lector.

REGLAS OBLIGATORIAS:
- Objetivo: entre 800 y 1200 palabras por artículo.
- No rellenes para alcanzar la extensión. Si la fuente no tiene suficiente
  información, redactará una nota más corta y fiel, sin inventar hechos.
- Usá únicamente hechos, cifras, nombres, fechas y declaraciones presentes.
  en el texto base. No agregues antecedentes externos ni supongas consecuencias.
- No inventes citas, fuentes, declaraciones, cifras ni detalles.
- No repita ideas para sumar palabras.
- Redactá con estructura propia; no copias párrafos de la fuente ni reproduzcas
  más de 6 palabras seguidas del texto base.
- Separará los hechos confirmados de las posibilidades.
- Si no hay una noticia real o información suficiente y fiable, deja "artículo" vacío.
- Tratá cada nota por separado. No mezcles datos entre notas.
- Texto plano, con párrafos separados por una línea en blanco. Rebaja del pecado,
  asteriscos, numerales ni viñetas. Ignora menús, publicidad y enlaces relacionados.
- Empezá por el hecho principal, desarrollará los detalles disponibles y cerrará
  con un párrafo informativo sin inventar conclusiones.

Elegí "categoria" entre: Mundo, Sociedad, Economía, Tecnología, Deportes, Ciencia.

Devolvé SOLO JSON válido:
{"notas":[{"indice":1,"titulo":"título en español, máximo 120 caracteres",
"resumen":"1 o 2 oraciones, máximo 200 caracteres","categoria":"categoría válida",
"articulo":"nota completa en texto plano"}]}
Incluí una entrada por nota con el mismo número de índice.

__NOTAS__
"""


# ============================================================
# LIMPIEZA Y FECHAS
# ============================================================

def limpiar_html(texto):
    texto = re.sub(r"<[^>]+>", " ", texto o "")
    return re.sub(r"\s+", " ", html.unescape(texto)).strip()


def limpiar_texto_articulo(texto):
    texto = re.sub(r"<[^>]+>", "", str(texto o ""))
    texto = texto.reemplazar("**", "").reemplazar("__", "")
    texto = re.sub(r"(?m)^\s*#+\s*", "", texto)
    texto = re.sub(r"(?m)^\s*[-*•]\s+", "", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    devolver texto.strip()


def fecha_publicacion(entrada):
    para campo en ("published_parsed", "updated_parsed", "created_parsed"):
        valor = entrada.get(campo)
        si valor:
            intentar:
                segundos = calendario.timegm(valor)
                devolver fecha y hora.fromtimestamp(segundos, tz=UTC)
            excepto (ValueError, TypeError, OverflowError):
                aprobar

    para campo en ("publicado", "actualizado", "creado"):
        valor = entrada.get(campo)
        si valor:
            intentar:
                fecha = parsedate_to_datetime(valor)
                Si fecha.tzinfo es None:
                    fecha = fecha.replace(tzinfo=UTC)
                devolver fecha.astimezone(UTC)
            excepto (ValueError, TypeError, OverflowError):
                intentar:
                    fecha = fechahora.fromisoformat(valor.replace("Z", "+00:00"))
                    Si fecha.tzinfo es None:
                        fecha = fecha.replace(tzinfo=UTC)
                    devolver fecha.astimezone(UTC)
                excepto (ValueError, TypeError, OverflowError):
                    aprobar

    devolver Ninguno


def imagen_de_entrada(entrada):
    para grupo en (
        entrada.get("contenido_media", []),
        entrada.get("media_thumbnail", []),
    ):
        para medios en grupo:
            Si media.get("url"):
                devolver media["url"]

    para cada recinto en entry.get("enclosures", []):
        si (
            recinto.get("tipo", "").startswith("imagen")
            y enclosure.get("href")
        ):
            devolver el recinto["href"]

    devolver IMAGEN_POR_DEFECTO


# ============================================================
# DESCARGAS CON TIEMPO LIMITE
# ============================================================

def obtener_contenido_completo(url):
    """Descarga una página con tiempo de espera y extrae su texto principal."""
    intentar:
        respuesta = requests.get(
            URL,
            encabezados={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; PanoramaGlobalNews/1.0)"
                )
            },
            tiempo_de_espera=(TIEMPO_DE_CONEXIÓN, TIEMPO_DE_ESPERA_ARTÍCULO),
        )
        respuesta.raise_for_status()

        texto = trafilatura.extract(respuesta.texto)

        si texto y len(texto) > MIN_TEXTO_BASE:
            texto de retorno

    excepto requests.RequestException como error:
        print(f"Error/tiempo de espera descargando artículo {url}: {error}")
    excepto Exception como error:
        print(f"Error al extraer el artículo {url}: {error}")

    devolver Ninguno


def texto_util(texto):
    devolver bool(
        texto
        y len(texto.strip()) >= MIN_TEXTO_BASE
        y no texto.strip().startswith("Watch CBS News")
    )


# ============================================================
# GÉMINIS
# ============================================================

def es_error_cuota(error):
    mensaje = str(error).lower()

    devolver cualquiera(
        palabra en mensaje
        para palabra en (
            "429",
            "cuota",
            "límite de velocidad",
            "recursos agotados",
            "demasiadas peticiones",
        )
    )


def es_bloqueo(error):
    mensaje = str(error).lower()

    devolver cualquiera(
        palabra en mensaje
        para palabra en (
            "block_reason",
            "contenido prohibido",
            "prompt_feedback",
        )
    )


def construir_prompt(lote):
    bloques = []

    para i, pendiente en enumerate(lote, start=1):
        texto = str(pendiente.get("rawText") o "")[
            :MAX_TEXTO_POR_NOTA
        ]

        bloques.append(
            f"=== NOTA {i} ===\n"
            f"TÍTULO ORIGINAL: {pendiente.get('título', '')}\n"
            f"TEXTO BASE:\n{texto}"
        )

    devolver (
        PROMPT.replace("__CANTIDAD__", str(len(lote)))
        .replace("__NOTAS__", "\n\n".join(bloques))
    )


def pedir_a_gemini(lote):
    """Devuelve (lista de notas, bloqueada)."""

    si el modelo es Ninguno o estado_ia["cuota_agotada"]:
        devolver Ninguno, Falso

    if estado_ia["llamadas"] >= MAX_LLAMADAS_POR_EJECUCION:
        print("Límite de llamadas a Gemini alcanzado.")
        devolver Ninguno, Falso

    if estado_ia["llamadas"] > 0:
        tiempo.dormir(PAUSA_ENTRE_LLAMADAS)

    estado_ia["llamadas"] += 1

    intentar:
        respuesta = model.generate_content(
            construir_prompt(lote),
            configuración_generación={
                "response_mime_type": "application/json",
                "temperatura": 0,4,
                "max_output_tokens": 16384,
            },
            request_options={"timeout": TIMEOUT_GEMINI},
        )

        texto = (respuesta.text o "").strip() si respuesta else ""
        texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)

        si no es texto:
            rise ValueError("Gemini devolvió una respuesta vacía.")

        datos = json.loads(texto)
        notas = datos.get("notas") if isinstance(datos, dict) else datos

        si no es una instancia (notas, lista):
            rise ValueError("La respuesta no contiene una lista de notas.")

        estado_ia["fallos_seguidos"] = 0
        devolver notas, Falso

    excepto Exception como error:
        print(f"Error IA: {error}")

        si es_bloqueo(error):
            print("Gemini bloqueó este lote por contenido sensible.")
            devolver Ninguno, Verdadero

        si es_error_cuota(error):
            estado_ia["cuota_agotada"] = Verdadero
            print("Cuota agotada; las notas restantes quedan en cola.")
            devolver Ninguno, Falso

        estado_ia["fallos_seguidos"] += 1
        devolver Ninguno, Falso


# ============================================================
# ARCHIVOS JSON
# ============================================================

def cargar_json(ruta, valor_predeterminado):
    Si no existe os.path.ruta(ruta):
        devolver valor_predeterminado

    intentar:
        con open(ruta, "r", encoding="utf-8") como archivo:
            devolver json.load(archivo)
    excepto (json.JSONDecodeError, OSError) como error:
        print(f"Error leyendo {ruta}: {error}")
        devolver valor_predeterminado


def guardar_json(ruta, datos):
    directorio = os.path.dirname(ruta)

    si directorio:
        os.makedirs(directorio, exist_ok=True)

    temporal = ruta + ".tmp"

    con open(temporal, "w", encoding="utf-8") como archivo:
        json.dump(datos, archivo, asegurar_ascii=False, sangría=2)
        archivo.write("\n")

    os.replace(temporal, ruta)


# ============================================================
# VALIDACIÓN DE NOTICIAS
# ============================================================

def es_noticia_demo(noticia):
    fuente = limpiar_html(noticia.get("fuente", "")).casefold()
    titulo = limpiar_html(noticia.get("title", "")).casefold()
    identificador = str(noticia.get("id", ""))

    si fuente en FUENTES_DEMO:
        devolver verdadero

    si identificador en {"1", "2", "3", "4", "5"}:
        devolver verdadero

    return any(frase in titulo for frase in FRASES_DEMO)


def convertir_fecha(texto):
    si no es texto:
        devolver Ninguno

    intentar:
        texto = str(texto).strip()

        si "T" en el texto:
            fecha = fechahora.fromisoformat(
                texto.replace("Z", "+00:00")
            )
        demás:
            fecha = datetime.strptime(
                texto[:10], "%Y-%m-%d"
            ).reemplazar(tzinfo=UTC)

        Si fecha.tzinfo es None:
            fecha = fecha.replace(tzinfo=UTC)

        devolver fecha.astimezone(UTC)

    excepto (ValueError, TypeError, OverflowError):
        devolver Ninguno


def preparar_noticia(datos, pendiente):
    Si no es una instancia (datos, dict):
        devolver Ninguno

    articulo = limpiar_texto_articulo(datos.get("articulo"))
    palabras = len(articulo.split())

    # No publicar artículos demasiado cortos.
    si palabras < MIN_PALABRAS_ARTICULO:
        imprimir(
            f"Artículo muy corto ({palabras} palabras): "
            f"{pendiente.get('title', '')[:80]}"
        )
        devolver Ninguno

    título = limpiar_html(
        str(datos.get("titulo") o "")
    ) o pendiente["título"]

    resumen = limpiar_html(str(datos.get("resumen") o ""))

    si no resumen:
        resumen = limpiar_html(articulo)[:200] + "..."

    categoria = str(datos.get("categoria") or "").strip()

    si la categoría no está en CATEGORIAS_VALIDAS:
        categoria = pendiente.get("categoria", "Mundo")

    si la categoría no está en CATEGORIAS_VALIDAS:
        categoría = "Mundo"

    fecha = (
        convertir_fecha(pendiente.get("publicadoEn"))
        o datetime.now(UTC)
    )

    devolver {
        "id": pendiente["id"],
        "título": título[:300],
        "summary": resumen[:300],
        "contenido": artículo,
        "source": pendiente.get("source", "Fuente RSS"),
        "sourceUrl": pendiente["sourceUrl"],
        "fecha": fecha.astimezone(ZONA_AR).strftime("%Y-%m-%d"),
        "publicadoEn": fecha.isoformat(),
        "categoría": categoria,
        "imageUrl": pendiente.get("imageUrl") o IMAGEN_POR_DEFECTO,
    }


# ============================================================
# PROCESO PRINCIPAL
# ============================================================

def ejecutar():
    ahora = datetime.now(UTC)
    limite = ahora - timedelta(horas=HORAS_MAXIMAS)

    si el modelo:
        print(f"IA configurada: {MODELO_IA}")
    demás:
        imprimir(
            "ATENCIÓN: no hay clave de Gemini; "
            "solo se actualizará la cola."
        )

    anteriores = cargar_json(NEWS_FILE_PATH, [])

    si no es una instancia (anteriores, lista):
        anteriores = []

    pendientes = cargar_json(PENDING_FILE_PATH, [])

    si no es una instancia(pendientes, lista):
        pendientes = []

    # 1. Conservar noticias anteriores válidas de hasta 7 días.
    noticias = []
    urls_publicadas = set()
    títulos_publicados = set()
    ids_publicados = set()

    para noticias en anteriores:
        si no es una instancia(noticia, dict):
            continuar

        si es_noticia_demo(noticia):
            continuar

        fecha = convertir_fecha(
            noticia.get("publishedAt") o noticia.get("date")
        )

        si no fecha:
            continuar

        si fecha < límite:
            continuar

        si fecha > ahora + timedelta(minutos=5):
            continuar

        enlace = str(noticia.get("sourceUrl") or "").strip()
        título = limpiar_html(
            noticia.get("título", "")
        ).casefold()

        if enlace y enlace en urls_publicadas:
            continuar

        si titulo y titulo en titulos_publicados:
            continuar

        noticias.append(noticia)

        si enlace:
            urls_publicadas.add(enlace)

        si título:
            titulos_publicados.add(titulo)

        si noticia.get("id"):
            ids_publicados.add(str(noticia["id"]))

    # 2. Recuperar pendientes de ejecuciones anteriores.
    cola = []
    urls_en_cola = set()
    títulos_en_cola = set()

    para pendiente en pendientes:
        si no es instancia(pendiente, dict):
            continuar

        enlace = str(pendiente.get("sourceUrl") or "").strip()
        fecha = convertir_fecha(pendiente.get("publicadoEn"))

        Si no hay enlace o no hay fecha:
            continuar

        if fecha < limite o fecha > ahora + timedelta(minutos=5):
            continuar

        si enlace en urls_publicadas o enlace en urls_en_cola:
            continuar

        si no texto_util(str(pendiente.get("rawText") o "")):
            continuar

        cola.append(pendiente)
        urls_en_cola.add(enlace)
        títulos_en_cola.add(
            limpiar_html(pendiente.get("título", "")).casefold()
        )

    # 3. Buscar noticias nuevas en fuentes RSS con tiempo de espera.
    inicio = (ahora.hora // 6 * 5) % len(RSS_FEEDS)
    feeds = RSS_FEEDS[inicio:] + RSS_FEEDS[:inicio]
    candidatas_nuevas = 0

    para feed_url, categoria en feeds:
        Si len(cola) >= MAX_COLA:
            romper

        si candidatas_nuevas >= MAX_CANDIDATAS_NUEVAS:
            romper

        intentar:
            respuesta = requests.get(
                URL del feed,
                encabezados={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; PanoramaGlobalNews/1.0)"
                    )
                },
                tiempo_de_espera=(TIEMPO_DE_CONEXIÓN, TIEMPO_DE_ESPERA_RSS),
            )

            respuesta.raise_for_status()
            feed = feedparser.parse(respuesta.content)

        excepto requests.RequestException como error:
            print(f"Error/tiempo de espera agotado RSS {feed_url}: {error}")
            continuar

        excepto Exception como error:
            print(f"Error leyendo RSS {feed_url}: {error}")
            continuar

        si no hay feed.entradas:
            print(f"RSS sin entradas: {feed_url}")
            continuar

        vistas = 0

        para entrada en feed.entries:
            Si vistas >= POR_FUENTE:
                romper

            Si len(cola) >= MAX_COLA:
                romper

            si candidatas_nuevas >= MAX_CANDIDATAS_NUEVAS:
                romper

            título = limpiar_html(entrada.get("título", ""))
            enlace = str(entry.get("link") or "").strip()

            resumen_rss = limpiar_html(
                entrada.get("summary", "")
                o entrada.get("descripción", "")
            )

            fecha = fecha_publicacion(entrada)

            si no título o no enlace o no fecha:
                continuar

            si fecha < límite:
                continuar

            si fecha > ahora + timedelta(minutos=5):
                continuar

            si enlace en urls_publicadas o enlace en urls_en_cola:
                continuar

            si titulo.casefold() en titulos_publicados:
                continuar

            si titulo.casefold() en titulos_en_cola:
                continuar

            identificador = hashlib.sha1(
                enlace.encode("utf-8")
            ).hexdigest()[:16]

            si identificador en ids_publicados:
                continuar

            texto_crudo = (
                obtener_contenido_completo(enlace)
                o resumen_rss
            )

            si no texto_util(texto_crudo):
                print(f"Texto insuficiente; se omite: {titulo[:80]}")
                continuar

            cola.append({
                "id": identificador,
                "título": título,
                "source": limpiar_html(
                    feed.feed.get("title", "Fuente RSS")
                )[:100],
                "sourceUrl": enlace,
                "publicadoEn": fecha.isoformat(),
                "categoría": categoria,
                "imageUrl": imagen_de_entrada(entrada),
                "rawText": texto_crudo[:MAX_TEXTO_POR_NOTA],
                "intentos": 0,
            })

            urls_en_cola.add(enlace)
            titulos_en_cola.add(titulo.casefold())
            vistas += 1
            candidatas_nuevas += 1

    # 4. Redactar noticias en lotes pequeños para evitar JSON truncado.
    cola.sort(
        key=lambda pendiente: pendiente.get("publicadoEn", ""),
        reverso=Verdadero,
    )

    cola_restante = []
    publicadas_ahora = 0
    posición = 0

    mientras posición < len(cola):
        puede_llamar = (
            El modelo no es ninguno.
            y no estado_ia["cuota_agotada"]
            and estado_ia["llamadas"] < MAX_LLAMADAS_POR_EJECUCION
            y estado_ia["fallos_seguidos"] < MAX_FALLOS_SEGUIDOS
        )

        si no puede_llamar:
            cola_restante.extend(cola[posicion:])
            romper

        if cola[posicion].get("solo"):
            lote = [cola[posición]]
        demás:
            lote = []

            para candidata en cola[
                posicion:posicion + NOTAS_POR_LLAMADA
            ]:
                si candidata.get("solo"):
                    romper

                lote.append(candidata)

        posición += len(lote)

        notas, bloqueado = pedir_a_gemini(lote)

        resultados = {}

        para nota en notas o []:
            si no es una instancia(nota, dict):
                continuar

            intentar:
                resultados[int(nota.get("índice"))] = nota
            excepto (TypeError, ValueError):
                aprobar

        para i, pendiente en enumerate(lote, start=1):
            si bloqueado:
                Si len(lote) == 1:
                    imprimir(
                        "Géminis bloqueó la nota; se descarta: "
                        f"{pendiente['title'][:80]}"
                    )
                demás:
                    pendiente["solo"] = Verdadero
                    cola_restante.append(pendiente)

                continuar

            noticia = preparar_noticia(
                resultados.get(i),
                pendiente,
            )

            si noticia:
                noticias.append(noticia)

                urls_publicadas.add(pendiente["origenUrl"])
                títulos_publicados.add(
                    noticia["título"].casefold()
                )
                ids_publicados.add(str(noticia["id"]))

                publicadas_ahora += 1
                continuar

            si no estado_ia["cuota_agotada"]:
                pendiente["intentos"] = (
                    int(pendiente.get("intentos", 0)) + 1
                )

                if pendiente["intentos"] >= MAX_INTENTOS_NOTA:
                    imprimir(
                        "Se descarta tras varios intentos: "
                        f"{pendiente['title'][:80]}"
                    )
                    continuar

            cola_restante.append(pendiente)

    # 5. Limpiar cola y ordenar noticias.
    cola_restante = [
        pendiente
        para pendiente en cola_restante
        si pendiente.get("sourceUrl") no está en urls_publicadas
    ][:MAX_COLA]

    noticias.sort(
        clave=lambda noticia: noticia.get("publicadoEn", ""),
        reverso=Verdadero,
    )

    # Si no quedan noticias válidas, intentar conservar las anteriores
    # en vez de reemplazar news.json por una lista vacía.
    si no noticias y anteriores:
        conservadas = [
            noticia
            para noticias en anteriores
            si isinstance(noticia, dict)
            y no es_noticia_demo(noticia)
        ]

        si conservadas:
            imprimir(
                "No hay noticias nuevas válidas; "
                "se conserva el contenido anterior."
            )
            noticias = conservadas

    # Guardar usando archivos temporales para evitar escrituras parciales.
    guardar_json(
        RUTA_DE_ARCHIVO_DE_NOTICIAS,
        noticias[:MAX_NOTICIAS],
    )

    guardar_json(
        RUTA_DE_ARCHIVO_PENDIENTE,
        cola_restante,
    )

    imprimir(
        f"Proceso terminado: {publicadas_ahora} noticias nuevas; "
        f"{len(cola_restante)} en cola; "
        f"{min(len(noticias), MAX_NOTICIAS)} publicadas; "
        f"{estado_ia['llamadas']} llama a Gemini"
        + (
            "; cuota agotada."
            si estado_ia["cuota_agotada"]
            demás "."
        )
    )


if __name__ == "__main__":
    ejecutar()
