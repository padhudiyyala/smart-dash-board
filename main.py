import os
import json
import httpx
import uvicorn
import psutil
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from google import genai

# =====================================================================
# CONFIGURATION & VERIFIED HARDCODED API KEYS
# =====================================================================
NEWS_API_KEY = "087d5909ef8249eb8d6cad03d9a72fa5"
GEMINI_API_KEY = "AQ.Ab8RN6LJGv6u0uAFQrCBpd05BwYwxFLMASl598EqsjoHKxX4fQ"

ai_client = None
if GEMINI_API_KEY:
    ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Global variables to act as a temporary cache and save API calls
cached_weather = {"temperature": "32°C", "humidity": "65%", "city": "Vijayawada"}
cached_news = {"headline": "AI innovation and tech ecosystems transforming software workflows globally."}
cached_ai = {
    "quote": "Success comes from consistency, not perfection.",
    "suggestion": "Complete your highest-priority task before noon today."
}

# =====================================================================
# DATABASE SETUP (SQLite)
# =====================================================================
DATABASE_URL = "sqlite:///./dashboard.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    completed = Column(Boolean, default=False)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# =====================================================================
# API FETCHERS WITH CACHE PROTECTION
# =====================================================================
async def fetch_weather_data(city: str = "Vijayawada"):
    global cached_weather
    lat, lon = 16.5062, 80.6480
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=4.0)
            if response.status_code == 200:
                data = response.json()
                current = data.get("current_weather", {})
                temp = current.get("temperature")
                cached_weather = {
                    "temperature": f"{round(temp)}°C" if temp is not None else "32°C",
                    "humidity": "72%", 
                    "city": city
                }
        except Exception as e:
            print(f"Weather Fetch Warning (Using Cache): {e}")
    return cached_weather

async def fetch_news_data():
    global cached_news
    url = f"https://newsapi.org/v2/top-headlines?country=in&pageSize=1&apiKey={NEWS_API_KEY}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=4.0)
            if response.status_code == 200:
                articles = response.json().get("articles", [])
                if articles:
                    cached_news = {"headline": articles[0]["title"]}
        except Exception as e:
            print(f"News Fetch Warning (Using Cache): {e}")
    return cached_news

def generate_ai_content():
    global cached_ai
    if not ai_client:
        return cached_ai
    try:
        prompt = (
            "Provide a brief productivity suggestion. "
            "Output exactly raw JSON containing keys 'quote' and 'suggestion'. "
            "Do not wrap the output in markdown code blocks like ```json."
        )
        response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        clean_text = response.text.strip().replace("```json", "").replace("```", "")
        cached_ai = json.loads(clean_text)
    except Exception as e:
        print(f"Gemini Fetch Warning (Using Cache): {e}")
    return cached_ai

# =====================================================================
# FASTAPI CONTROLLER & PIPELINE ENTRY POINTS
# =====================================================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/tasks")
def add_new_task(title: str, db: Session = Depends(get_db)):
    if not title.strip():
        raise HTTPException(status_code=400, detail="Task text invalid")
    db_task = Task(title=title)
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return {"status": "success"}

# FAST LIGHTWEIGHT ROUTE: Only fetches hardware + tasks + cached layout entries
@app.get("/api/dashboard/fast")
def get_fast_dashboard(db: Session = Depends(get_db)):
    db_tasks = db.query(Task).filter(Task.completed == False).all()
    tasks_list = [{"id": task.id, "title": task.title} for task in db_tasks]
    
    return {
        "system_hardware": {
            "cpu": round(psutil.cpu_percent(interval=None)),
            "ram": round(psutil.virtual_memory().percent)
        },
        "cricket": {
            "match": "IND vs AUS (T20 International)",
            "score": "IND: 184/3",
            "overs": "18.2 Ovs",
            "status": "India need 22 runs in 10 balls. Target: 206"
        },
        "tasks": tasks_list,
        "weather": cached_weather,
        "news": cached_news,
        "ai_productivity": cached_ai
    }

# HEAVY COMPREHENSIVE ROUTE: Refreshes real third-party connections
@app.get("/api/dashboard/all")
async def get_full_dashboard(city: str = "Vijayawada", db: Session = Depends(get_db)):
    await fetch_weather_data(city)
    await fetch_news_data()
    generate_ai_content()
    return get_fast_dashboard(db)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)