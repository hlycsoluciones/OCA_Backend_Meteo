import os
import sqlite3
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from openai import OpenAI
import httpx

# ===========================================================
# CONFIG
# ===========================================================

AEMET_API_KEY = os.getenv("AEMET_KEY")
OPENAI_KEY = os.getenv("OPENAI_KEY")

client = OpenAI(api_key=OPENAI_KEY)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===========================================================
# DATABASE
# ===========================================================

DB = "meteo_history.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS history (
            ts TEXT,
            temp REAL,
            humedad REAL,
            lluvia REAL,
            presion REAL,
            cielo TEXT,
            PRIMARY KEY(ts)
        )
    """)
    conn.commit()
    conn.close()

init_db()

def save_to_history(data):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    for row in data:
        c.execute("""
            INSERT OR REPLACE INTO history (ts,temp,humedad,lluvia,presion,cielo)
            VALUES (?,?,?,?,?,?)
        """, (
            row["ts"], row["temp"], row["humedad"], row["lluvia"],
            row.get("presion", None),
            row.get("cielo", None)
        ))
    conn.commit()
    conn.close()

# ===========================================================
# MODELOS
# ===========================================================

class AskModel(BaseModel):
    question: str
    location: Optional[str] = "Noia"

# ===========================================================
# AEMET + METEOGALICIA
# ===========================================================

async def get_aemet():
    url = f"https://opendata.aemet.es/opendata/api/prediccion/especifica/municipio/diaria/15064/?api_key={AEMET_API_KEY}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        if r.status_code != 200:
            return None
        data_url = r.json().get("datos")
        if not data_url:
            return None
        r2 = await client.get(data_url)
        return r2.json()

async def get_meteogalicia():
    url = "https://servizos.meteogalicia.gal/mgrss/predicion/jsonPredConcellos.action?idConc=15064"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        return r.json()

# ===========================================================
# ENDPOINT → datos combinados
# ===========================================================

@app.get("/meteo/combined")
async def combined():
    aemet = await get_aemet()
    meteo = await get_meteogalicia()

    resultado = []

    try:
        hoy = aemet[0]["prediccion"]["dia"][0]
        for hora in hoy["temperatura"]:
            resultado.append({
                "ts": hora["fecha"],
                "temp": hora["value"],
                "humedad": 95,
                "lluvia": hoy.get("probPrecipitacion", [{}])[0].get("value", 0),
                "presion": None,
                "cielo": hoy["estadoCielo"][0].get("descripcion","")
            })
    except:
        pass

    save_to_history(resultado)

    return resultado

# ===========================================================
# ENDPOINT → IA lluvia
# ===========================================================

@app.get("/meteo/ai_rain")
async def ai_rain():
    data = await combined()

    prompt = f"""
    Con los siguientes datos meteorológicos:
    {data}

    Devuélveme SOLO un número entre 0 y 100 que indique la probabilidad de lluvia.
    """

    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )

    try:
        text = resp.output_text.strip()
        prob = int(''.join(filter(str.isdigit, text))[:3])
    except:
        prob = 50

    return {"prob_lluvia": prob}

# ===========================================================
# ENDPOINT → Chat IA con localización
# ===========================================================

@app.post("/chatgpt")
async def chatIA(data: AskModel):
    prompt = f"""
    Actúa como meteorólogo experto en Galicia.

    Ubicación consultada: {data.location}

    Pregunta del usuario:
    {data.question}

    Usa histórico local si es útil y explica la probabilidad de lluvia,
    presión, viento, humedad y anomalías.
    """

    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )

    return {"reply": resp.output_text}

# ===========================================================
# ROOT
# ===========================================================

@app.get("/")
async def root():
    return {"status": "OK", "mensaje": "OCA Sistem Meteo API activa"}
