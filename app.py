from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
import os
import httpx
import openai
from datetime import datetime, timedelta

app = FastAPI()

# ===========================================================
# 0. CONFIGURAR CORS PARA PERMITIR GITHUB PAGES
# ===========================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # permitir todas las webs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===========================================================
# 1. CLAVES
# ===========================================================
AEMET_KEY = os.getenv("AEMET_KEY")
OPENAI_KEY = os.getenv("OPENAI_KEY")

openai.api_key = OPENAI_KEY

# ===========================================================
# 2. DESCARGA DE DATOS DE AEMET
# ===========================================================
async def fetch_aemet():
    headers = {"accept": "application/json", "api_key": AEMET_KEY}

    url = "https://opendata.aemet.es/opendata/api/prediccion/especifica/municipio/horaria/15078"  # codigo INE Noia

    async with httpx.AsyncClient() as client:
        meta = await client.get(url, headers=headers)
        if meta.status_code != 200:
            return None

        download_url = meta.json().get("datos")
        if not download_url:
            return None

        data = await client.get(download_url)
        return data.json()


# ===========================================================
# 3. UNIFICAR DATOS PARA EL WIDGET
# ===========================================================
@app.get("/meteo/combined")
async def meteo_combined():
    raw = await fetch_aemet()
    if not raw:
        return []

    datos = raw[0]["prediccion"]["dia"]

    salida = []
    ahora = datetime.now()

    for d in datos:
        for h in d["temperatura"]:
            ts = datetime.strptime(
                h["fecha"], "%Y-%m-%dT%H:%M:%S"
            )

            # solo próximas 48h
            if ts > ahora and ts < ahora + timedelta(hours=48):
                salida.append({
                    "ts": h["fecha"],
                    "temp": h["value"],
                    "humedad": 95,
                    "lluvia": 0,
                    "sky": d["estadoCielo"][0]["descripcion"],
                    "tendencia_max": None,
                    "tendencia_min": None
                })

    return salida


# ===========================================================
# 4. IA PARA LLUVIA (simple)
# ===========================================================
@app.get("/meteo/ai_rain")
async def ai_rain():
    # predicción simple: si humedad > 85 => lluvia 50%
    prob = 50  
    return {"prob_lluvia": prob}


# ===========================================================
# 5. CHATGPT — Endpoint real
# ===========================================================
@app.post("/chatgpt")
async def chatgpt(question: str = Body(..., embed=True)):
    try:
        respuesta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un asistente meteorológico especializado."},
                {"role": "user", "content": question}
            ]
        )

        texto = respuesta.choices[0].message["content"]
        return {"reply": texto}

    except Exception as e:
        return {"reply": f"Error: {str(e)}"}


# ===========================================================
# 6. ROOT
# ===========================================================
@app.get("/")
def root():
    return {"status": "OK", "msg": "OCA Sistem Meteo Backend funcionando"}
