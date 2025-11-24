import os
import sqlite3
from datetime import datetime
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

    url = "https://servizos.meteogalicia.gal/apiv3/xml/observacionEstacionsMeteo"

    try:
        r = httpx.get(url, timeout=10)

        # *** FIX DECODIFICACIÓN ***
        text = r.content.decode("latin-1", errors="ignore")

        # EJEMPLO FAKE: debes reemplazar con parseo real
        data = [{
            "ts": datetime.now().isoformat(),
            "temp": 10.5,
            "humedad": 82,
            "lluvia": 0,
            "sky": "nubes altas",
            "tendencia_max": None,
            "tendencia_min": None
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
        prompt = """
        Basado en los últimos datos meteorológicos de Galicia,
        predice la probabilidad de lluvia en porcentaje.
        Solo responde con un número del 0 al 100.
        """

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )

        # *** FIX SUBSCRIPTABLE ***
        lluvia = resp.choices[0].message.content.strip()

        try:
            lluvia = int(lluvia)
        except:
            lluvia = 50

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
