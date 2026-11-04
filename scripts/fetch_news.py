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
MAX_TEXTO_POR_NOTA = 6000

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
    "https://images.unsplash.com/photo-150471143
