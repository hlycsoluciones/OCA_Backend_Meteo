import os
import sqlite3
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from typing import Optional
from openai import OpenAI

# ======================================
# CONFIG
# ======================================

AEMET_API_KEY = os.getenv("AEMET_KEY")
OPENAI_KEY = os.getenv("OPENAI_KEY")

client = OpenAI(api_key=OPENAI_KEY)

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================================
# BASE DE DATOS
# ======================================

DB = "meteo.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            temp REAL,
            humedad INTEGER,
            lluvia INTEGER,
            sky TEXT,
            tendencia_max REAL,
            tendencia_min REAL
        )
    """)
    conn.commit()
    conn.close()

init_db()

def save_to_history(d):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        INSERT INTO history (ts,temp,humedad,lluvia,sky,tendencia_max,tendencia_min)
        VALUES (?,?,?,?,?,?,?)
    """, (d["ts"], d["temp"], d["humedad"], d["lluvia"], d["sky"], d["tendencia_max"], d["tendencia_min"]))
    conn.commit()
    conn.close()
def get_recent_temps(days: int = 7):
    """
    Devuelve temperaturas de los últimos días
    """
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    limite = datetime.utcnow() - timedelta(days=days)
    c.execute(
        "SELECT temp FROM history WHERE ts >= ? ORDER BY ts DESC",
        (limite.isoformat(),)
    )

    filas = c.fetchall()
    conn.close()
    temps = [f[0] for f in filas if f[0] is not None]
    return temps


def compute_trend(current_temp: float, days: int = 7):
    """
    Calcula tendencias comparando la temperatura actual
    con valores máximos y mínimos recientes.
    """
    temps = get_recent_temps(days=days)

    if len(temps) < 3:
        return None, None

    max_hist = max(temps)
    min_hist = min(temps)

    tendencia_max = current_temp - max_hist
    tendencia_min = current_temp - min_hist

    return tendencia_max, tendencia_min


# ======================================
# MODELO IA
# ======================================

class AskModel(BaseModel):
    question: str
    location: Optional[str] = "Noia"

# ======================================
# ENDPOINTS
# ======================================

@app.get("/")
def root():
    return {"msg": "OCA Sistem Meteo Backend OK"}

# ---------------------------
# MÉTEO COMBINADO
# ---------------------------

@app.get("/meteo/combined")
async def combined():
    try:
        # Datos temporales hasta conectar AEMET
        current_temp = 10.5
        current_hum = 82
        current_rain = 0
        current_sky = "nubes altas"

        tendencia_max, tendencia_min = compute_trend(current_temp, days=7)

        data = [{
            "ts": datetime.now().isoformat(),
            "temp": current_temp,
            "humedad": current_hum,
            "lluvia": current_rain,
            "sky": current_sky,
            "tendencia_max": tendencia_max,
            "tendencia_min": tendencia_min,
        }]

        save_to_history(data[0])
        return data

    except Exception as e:
        return {"error": "combined_failed", "detail": str(e)}



# ---------------------------
# IA LLUVIA
# ---------------------------
@app.get("/meteo/ai_rain")
async def rain_ai():
    try:
        prompt = (
            "Basado en los últimos datos meteorológicos de Galicia, "
            "predice la probabilidad de lluvia en porcentaje. "
            "Solo responde con un número del 0 al 100."
        )

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres una IA meteorológica experta en Galicia."},
                {"role": "user", "content": prompt},
            ],
        )

        # Objeto ChatCompletionMessage
        mensaje = resp.choices[0].message
        texto_lluvia = mensaje.content.strip()

        # Extraer solo dígitos por si la IA responde "40%" o "40 de 100"
        solo_digitos = "".join(ch for ch in texto_lluvia if ch.isdigit())
        if solo_digitos:
            lluvia = int(solo_digitos)
        else:
            lluvia = 50  # valor por defecto de seguridad

        # Limitar entre 0 y 100 por si acaso
        lluvia = max(0, min(100, lluvia))

        return {"prob_lluvia": lluvia}

    except Exception as e:
        return {"error": "ai_failed", "detail": str(e)}


# ---------------------------
# CHAT GENERAL
# ---------------------------

@app.post("/chatgpt")
async def ask_ai(body: AskModel):

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres una IA meteorológica experta en Galicia."},
                {"role": "user", "content": f"Ubicación: {body.location}. Pregunta: {body.question}"}
            ]
        )

        # *** FIX SUBSCRIPTABLE ***
        reply = resp.choices[0].message.content

        return {"reply": reply}

    except Exception as e:
        return {"error": "ai_failed", "detail": str(e)}




