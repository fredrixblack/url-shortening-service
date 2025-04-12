from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
from redis import Redis
import os
from dotenv import load_dotenv
import random
import string
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with VM2's public IP or domain
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
# Database connection
conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)
cursor = conn.cursor()

# Redis connection
redis = Redis(host=os.getenv("REDIS_HOST"), port=int(os.getenv("REDIS_PORT")), decode_responses=True)

# Create table if not exists
cursor.execute("""
    CREATE TABLE IF NOT EXISTS urls (
        id SERIAL PRIMARY KEY,
        original_url TEXT NOT NULL,
        short_code VARCHAR(6) UNIQUE NOT NULL
    )
""")
conn.commit()

# Pydantic model for request body
class UrlRequest(BaseModel):
    original_url: str

def generate_short_code(length=6):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

@app.post("/shorten")
async def shorten_url(url: UrlRequest):
    original_url = url.original_url

    # Check cache
    cached_short = redis.get(original_url)
    if cached_short:
        return {"short_url": f"http://url-shortener-main/api/{cached_short}","v":1}

    # Generate unique short code
    while True:
        short_code = generate_short_code()
        cursor.execute("SELECT 1 FROM urls WHERE short_code = %s", (short_code,))
        if not cursor.fetchone():
            break

    # Store in DB
    cursor.execute("INSERT INTO urls (original_url, short_code) VALUES (%s, %s)", (original_url, short_code))
    conn.commit()

    # Cache result
    redis.setex(original_url, 3600, short_code)  # Cache for 1 hour

    return {"short_url": f"http://url-shortener-main/api/{short_code}","v":2}

@app.get("/{short_code}")
async def redirect_url(short_code: str):
    cached_url = redis.get(short_code)
    if cached_url:
        return {"original_url": cached_url,"version":2}

    cursor.execute("SELECT original_url FROM urls WHERE short_code = %s", (short_code,))
    result = cursor.fetchone()
    if result:
        redis.setex(short_code, 3600, result[0])  # Cache for 1 hour
        return {"original_url": result[0],"version":1}
    raise HTTPException(status_code=404, detail="URL not found")