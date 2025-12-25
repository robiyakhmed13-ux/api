"""
Hamyon API - Complete Backend for Finance Tracker Bot
Deploy this to your API Railway service
"""

import os
import csv
import io
from datetime import date, datetime, timedelta
from typing import Optional, Literal

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field
import psycopg

app = FastAPI(title="Hamyon API", version="1.0.0")

DATABASE_URL = os.getenv("DATABASE_URL")
API_KEY = os.getenv("API_KEY", "")  # shared secret between bot & API

if not DATABASE_URL:
    raise ValueError("Missing DATABASE_URL")

def get_conn():
    return psycopg.connect(DATABASE_URL)

def auth(api_key: str | None):
    """Validate API key if set"""
    if API_KEY and api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

# ══════════════════════════════════════════════════════════════════════════════
# MODELS
# ══════════════════════════════════════════════════════════════════════════════

class TransactionIn(BaseModel):
    telegram_id: int
    type: Literal["expense", "income", "debt"] = "expense"
    amount: int = Field(ge=0)
    category_key: str
    description: Optional[str] = None
    merchant: Optional[str] = None
    tx_date: Optional[date] = None
    source: str = "text"

class LanguageIn(BaseModel):
    telegram_id: int
    language: Literal["uz", "ru", "en"]

# ══════════════════════════════════════════════════════════════════════════════
# HEALTH
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
def health():
    return {"ok": True}

# ══════════════════════════════════════════════════════════════════════════════
# USER LANGUAGE
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/users/lang")
def set_user_lang(
    payload: LanguageIn,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-KEY"),
    x_api_secret: Optional[str] = Header(default=None, alias="X-API-SECRET")
):
    auth(x_api_key or x_api_secret)
    
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (telegram_id, language)
                VALUES (%s, %s)
                ON CONFLICT (telegram_id)
                DO UPDATE SET language = EXCLUDED.language
            """, (payload.telegram_id, payload.language))
            conn.commit()
    
    return {"ok": True, "language": payload.language}

@app.get("/users/lang")
def get_user_lang(
    telegram_id: int,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-KEY"),
    x_api_secret: Optional[str] = Header(default=None, alias="X-API-SECRET")
):
    auth(x_api_key or x_api_secret)
    
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT language FROM users WHERE telegram_id = %s",
                (telegram_id,)
            )
            row = cur.fetchone()
    
    return {"language": row[0] if row else "uz"}

# ══════════════════════════════════════════════════════════════════════════════
# TRANSACTIONS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/transactions")
def create_transaction(
    payload: TransactionIn,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-KEY"),
    x_api_secret: Optional[str] = Header(default=None, alias="X-API-SECRET")
):
    auth(x_api_key or x_api_secret)
    
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO transactions 
                (telegram_id, type, amount, category_key, description, merchant, tx_date, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                payload.telegram_id,
                payload.type,
                payload.amount,
                payload.category_key,
                payload.description,
                payload.merchant,
                payload.tx_date,
                payload.source,
            ))
            row = cur.fetchone()
            conn.commit()
    
    return {"ok": True, "id": str(row[0])}

# Legacy endpoint for compatibility
@app.post("/sync/tx")
def create_tx_legacy(
    payload: dict,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-KEY")
):
    auth(x_api_key)
    
    user_id = payload.get("user_id") or payload.get("telegram_id")
    ttype = payload.get("type", "expense")
    amount = payload.get("amount")
    category = payload.get("category") or payload.get("category_key", "other")
    
    if not user_id or amount is None:
        raise HTTPException(400, "Missing fields")
    
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO transactions (telegram_id, type, amount, category_key, source)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (user_id, ttype, amount, category, payload.get("source", "bot")))
            new_id = cur.fetchone()[0]
            conn.commit()
    
    return {"id": str(new_id)}

# ══════════════════════════════════════════════════════════════════════════════
# STATISTICS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/stats/today")
def stats_today(
    telegram_id: int,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-KEY"),
    x_api_secret: Optional[str] = Header(default=None, alias="X-API-SECRET")
):
    auth(x_api_key or x_api_secret)
    today = date.today()
    
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COALESCE(SUM(CASE WHEN type = 'expense' THEN amount END), 0) AS expense,
                    COALESCE(SUM(CASE WHEN type = 'income' THEN amount END), 0) AS income,
                    COALESCE(SUM(CASE WHEN type = 'debt' THEN amount END), 0) AS debt,
                    COUNT(*) AS count
                FROM transactions
                WHERE telegram_id = %s
                  AND COALESCE(tx_date, created_at::date) = %s
            """, (telegram_id, today))
            row = cur.fetchone()
    
    return {
        "expense": row[0],
        "income": row[1],
        "debt": row[2],
        "count": row[3]
    }

@app.get("/stats/range")
def stats_range(
    telegram_id: int,
    days: int = 7,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-KEY"),
    x_api_secret: Optional[str] = Header(default=None, alias="X-API-SECRET")
):
    auth(x_api_key or x_api_secret)
    since = date.today() - timedelta(days=days - 1)
    
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COALESCE(SUM(CASE WHEN type = 'expense' THEN amount END), 0) AS expense,
                    COALESCE(SUM(CASE WHEN type = 'income' THEN amount END), 0) AS income,
                    COALESCE(SUM(CASE WHEN type = 'debt' THEN amount END), 0) AS debt,
                    COUNT(*) AS count
                FROM transactions
                WHERE telegram_id = %s
                  AND COALESCE(tx_date, created_at::date) >= %s
            """, (telegram_id, since))
            row = cur.fetchone()
    
    return {
        "expense": row[0],
        "income": row[1],
        "debt": row[2],
        "count": row[3],
        "since": str(since)
    }

# ══════════════════════════════════════════════════════════════════════════════
# EXPORT
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/export/csv")
def export_csv(
    telegram_id: int,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-KEY"),
    x_api_secret: Optional[str] = Header(default=None, alias="X-API-SECRET")
):
    auth(x_api_key or x_api_secret)
    
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    created_at, 
                    type, 
                    amount, 
                    category_key, 
                    description, 
                    merchant, 
                    COALESCE(tx_date, created_at::date) AS day, 
                    source
                FROM transactions
                WHERE telegram_id = %s
                ORDER BY created_at DESC
                LIMIT 2000
            """, (telegram_id,))
            rows = cur.fetchall()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["created_at", "type", "amount", "category", "description", "merchant", "date", "source"])
    for r in rows:
        writer.writerow(list(r))
    
    content = output.getvalue().encode("utf-8")
    return Response(content=content, media_type="text/csv")
