import os, json, math, sqlite3, threading, time, requests
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import openai

# =======================
# CONFIG / ENTORNO
# =======================
load_dotenv()

AEMET_KEY = os.getenv("AEMET_KEY", "")
OPENAI_KEY = os.getenv("OPENAI_KEY", "")
if OPENAI_KEY:
    openai.api_key = OPENAI_KEY

TZ = timezone(timedelta(hours=1))

app = FastAPI(title="OCA_Sistem_Meteo - Full System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =======================
# 1. METEOGALICIA (REAL)
# =======================
def fetch_meteogalicia():
    url = "https://servizos.meteogalicia.gal/mgrss/predicion/jsonCPrazo.action?dia=-1&request_locale=es"
    try:
        return requests.get(url, timeout=10).json()
    except:
        return None

def parse_meteogalicia(data):
    if not data:
        return []
    try:
        lista = data["listaPredicions"]
        today = lista[0]
        franxas = today["listaMapas"]
    except:
        return []

    now = datetime.now(TZ).replace(minute=0, second=0)
    out = []

    for fr in franxas:
        if fr["franxa"] == 1:
            start, end = now.replace(hour=7), now.replace(hour=14)
        elif fr["franxa"] == 2:
            start, end = now.replace(hour=14), now.replace(hour=20)
        else:
            start, end = now.replace(hour=20), (now+timedelta(days=1)).replace(hour=7)

        h = start
        while h < end:
            out.append({
                "ts": h.isoformat(),
                "sky": fr.get("titulo", ""),
                "tendMax": fr.get("tendMax"),
                "tendMin": fr.get("tendMin")
            })
            h += timedelta(hours=1)

    return out

# =======================
# 2. AEMET (REAL)
# =======================
def fetch_aemet(id_muni="15054"):
    if not AEMET_KEY:
        return []
    try:
        url = f"https://opendata.aemet.es/opendata/api/prediccion/especifica/municipio/diaria/{id_muni}?api_key={AEMET_KEY}"
        meta = requests.get(url).json()
        datos = requests.get(meta["datos"]).json()[0]["prediccion"]["dia"][0]
    except:
        return []

    tmax = datos["temperatura"]["maxima"]
    tmin = datos["temperatura"]["minima"]
    lluvia = datos["probPrecipitacion"][0].get("value", 0)
    hum = datos["humedadRelativa"]["maxima"]

    now = datetime.now(TZ).replace(minute=0, second=0)
    out = []
    for i in range(24):
        h = now + timedelta(hours=i)
        temp = tmin + (tmax - tmin) * math.sin((i/23)*math.pi)
        out.append({
            "ts": h.isoformat(),
            "temp": round(temp, 2),
            "humedad": hum,
            "lluvia": lluvia
        })
    return out

# =======================
# 3. MEZCLAR AEMET + MG
# =======================
def merge_sources(aemet, mg):
    out = []
    for i in range(min(len(aemet), len(mg))):
        out.append({
            "ts": aemet[i]["ts"],
            "temp": aemet[i]["temp"],
            "humedad": aemet[i]["humedad"],
            "lluvia": aemet[i]["lluvia"],
            "sky": mg[i]["sky"],
            "tendencia_max": mg[i]["tendMax"],
            "tendencia_min": mg[i]["tendMin"]
        })
    return out

# =======================
# 4. IA: probabilidad lluvia
# =======================
def ai_predict_rain(data):
    if not OPENAI_KEY:
        return 50

    prompt = (
        "Eres una IA meteorológica. Analiza la serie horaria y responde "
        "solo un número del 0 al 100 indicando probabilidad de lluvia:\n"
        + json.dumps(data)
    )

    try:
        res = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        text = res["choices"][0]["message"]["content"]
        num = int(''.join(filter(str.isdigit, text)))
        return max(0, min(100, num))
    except:
        return 50

# =======================
# 5. HISTÓRICO SQLite + JSON
# =======================
DB = "history.db"
os.makedirs("data", exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS history (
            ts TEXT,
            temp REAL,
            humedad REAL,
            lluvia REAL,
            sky TEXT,
            PRIMARY KEY(ts)
        )
    """)
    conn.commit()
    conn.close()

init_db()

def save_history(entry):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO history (ts, temp, humedad, lluvia, sky)
        VALUES (?, ?, ?, ?, ?)
    """, (entry["ts"], entry["temp"], entry["humedad"], entry["lluvia"], entry["sky"]))
    conn.commit()
    conn.close()

def save_json(entry):
    filename = f"data/history_{datetime.now().date()}.json"
    try:
        with open(filename, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except:
        pass

# =======================
# 6. TAREA AUTOMÁTICA CADA 10 MINUTOS
# =======================
def scheduler():
    while True:
        try:
            aemet = fetch_aemet()
            mg = parse_meteogalicia(fetch_meteogalicia())
            combined = merge_sources(aemet, mg)

            if combined:
                for entry in combined:
                    save_history(entry)
                    save_json(entry)

            print("✔ Datos guardados cada 10 min")
        except Exception as e:
            print("❌ Error en scheduler:", e)

        time.sleep(600)  # 10 minutos

threading.Thread(target=scheduler, daemon=True).start()

# =======================
# 7. ENDPOINTS
# =======================
@app.get("/meteo/aemet")
def api_aemet():
    return fetch_aemet()

@app.get("/meteo/mg")
def api_mg():
    return parse_meteogalicia(fetch_meteogalicia())

@app.get("/meteo/combined")
def api_combined():
    return merge_sources(fetch_aemet(), parse_meteogalicia(fetch_meteogalicia()))

@app.get("/meteo/ai_rain")
def api_ai():
    combined = api_combined()
    return {"prob_lluvia": ai_predict_rain(combined)}
