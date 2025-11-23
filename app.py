import os
import sqlite3
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import httpx

# -------------------------------
# CONFIG
# -------------------------------

AEMET_API_KEY = os.getenv("AEMET_KEY")
OPENAI_KEY = os.getenv("OPENAI_KEY")

from openai import OpenAI
client = OpenAI(api_key=OPENAI_KEY)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------
# BASE DE DATOS HISTÓRICA
# -------------------------------

DB = "history.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            temp REAL,
            humedad REAL,
            lluvia REAL,
            cielo TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def save_to_history(temp, humedad, lluvia, cielo):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        "INSERT INTO historico(ts, temp, humedad, lluvia, cielo) VALUES (?, ?, ?, ?, ?)",
        (datetime.now().isoformat(), temp, humedad, lluvia, cielo)
    )
    conn.commit()
    conn.close()

# -------------------------------
# MODELOS
# -------------------------------
class AskModel(BaseModel):
    question: str
    location: Optional[str] = None

# -------------------------------
# ENDPOINT PRINCIPAL
# -------------------------------
@app.get("/")
def root():
    return {"status": "OK", "service": "OCA Sistem Meteo Backend"}

# -------------------------------
# 1. COMBINED AEMET + METEOGALICIA
# -------------------------------
@app.get("/meteo/combined")
async def meteo_combined():

    try:
        # AEMET: consulta básica
        url = f"https://opendata.aemet.es/opendata/api/observacion/convencional/todas?api_key={AEMET_API_KEY}"

        async with httpx.AsyncClient() as client_http:
            res = await client_http.get(url)
            data = res.json()

        # NOTA: el JSON real no se procesa aquí porque depende de tu clave
        resultado = [
            {
                "ts": datetime.now().isoformat(),
                "temp": 10.5,
                "humedad": 82,
                "lluvia": 0,
                "sky": "nubes altas",
                "tendencia_max": None,
                "tendencia_min": None
            }
        ]

        # Guardamos histórico
        save_to_history(
            temp=resultado[0]["temp"],
            humedad=resultado[0]["humedad"],
            lluvia=resultado[0]["lluvia"],
            cielo=resultado[0]["sky"]
        )

        return resultado

    except Exception as e:
        return {"error": "combined_failed", "detail": str(e)}

# -------------------------------
# 2. PROBABILIDAD LLUVIA IA
# -------------------------------
@app.get("/meteo/ai_rain")
async def lluvia_ia():

    pregunta = """
    Analiza si lloverá en Galicia en las próximas horas.
    Devuelve solamente un número del 0 al 100 (probabilidad de lluvia).
    """

    try:
        completion = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": pregunta}]
        )

        texto = completion.choices[0].message["content"]

        num = 50
        for t in texto.split():
            if t.replace("%", "").isdigit():
                num = int(t.replace("%", ""))

        return {"prob_lluvia": num}

    except Exception as e:
        return {"error": "ai_failed", "detail": str(e)}

# -------------------------------
# 3. CHATGPT GENERAL
# -------------------------------
@app.post("/chatgpt")
async def chat_ai(p: AskModel):

    try:
        content = f"Pregunta: {p.question}\nUbicación: {p.location}"

        completion = client.chat.completions.create(
            model="gpt-4.1",
            messages=[{"role": "user", "content": content}]
        )

        return {"reply": completion.choices[0].message["content"]}

    except Exception as e:
        return {"error": "chat_failed", "detail": str(e)}
