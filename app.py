import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from openai import OpenAI

# ---------------------------------------------
# CONFIG
# ---------------------------------------------
AEMET_API_KEY = os.getenv("AEMET_KEY")
OPENAI_KEY = os.getenv("OPENAI_KEY")

client = OpenAI(api_key=OPENAI_KEY)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------
# MODELO PARA /chatgpt
# ---------------------------------------------
class ChatRequest(BaseModel):
    question: str

# ---------------------------------------------
# ENDPOINT: Probabilidad lluvia con IA
# ---------------------------------------------
@app.get("/meteo/ai_rain")
def ai_rain():
    return {"prob_lluvia": 50}   # ejemplo (luego lo mejoramos)

# ---------------------------------------------
# ENDPOINT: Datos combinados desde AEMET/MeteoGalicia
# ---------------------------------------------
@app.get("/meteo/combined")
async def combined():
    # Datos ficticios por ahora SOLO para que funcione la app
    datos = []
    for h in range(24):
        datos.append({
            "ts": f"2025-11-22T{h:02d}:00:00",
            "temp": 5 + h*0.3,
            "humedad": 95,
            "lluvia": 0,
            "sky": "",
            "tendencia_max": None,
            "tendencia_min": None
        })
    return datos

# ---------------------------------------------
# ENDPOINT: Pregunta a la IA
# ---------------------------------------------
@app.post("/chatgpt")
def chatgpt(req: ChatRequest):
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Eres una IA meteorológica experta."},
            {"role": "user", "content": req.question},
        ]
    )

    respuesta = r.choices[0].message.content
    return {"reply": respuesta}
