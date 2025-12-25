import os
from fastapi import FastAPI, Header, HTTPException
import psycopg

app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL")
API_KEY = os.getenv("API_KEY")  # simple shared secret between bot & API

if not DATABASE_URL:
    raise ValueError("Missing DATABASE_URL")

def get_conn():
    return psycopg.connect(DATABASE_URL)

def auth(x_api_key: str | None):
    if not API_KEY or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/sync/tx")
def create_tx(payload: dict, x_api_key: str | None = Header(default=None)):
    auth(x_api_key)
    # minimal example insert
    user_id = payload.get("user_id")
    ttype = payload.get("type")
    amount = payload.get("amount")
    category = payload.get("category")

    if not user_id or not ttype or amount is None:
        raise HTTPException(400, "Missing fields")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
              insert into transactions (user_id, type, amount, category, source)
              values (%s, %s, %s, %s, %s)
              returning id
            """, (user_id, ttype, amount, category, payload.get("source","bot")))
            new_id = cur.fetchone()[0]
            conn.commit()

    return {"id": new_id}
