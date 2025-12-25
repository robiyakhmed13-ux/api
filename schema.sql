-- Hamyon Database Schema
-- Run this in Railway PostgreSQL console

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    language TEXT NOT NULL DEFAULT 'uz',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Transactions table
CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('expense', 'income', 'debt')),
    amount BIGINT NOT NULL CHECK (amount >= 0),
    category_key TEXT NOT NULL,
    description TEXT,
    merchant TEXT,
    tx_date DATE,
    source TEXT NOT NULL DEFAULT 'text',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_transactions_telegram_time
ON transactions (telegram_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_transactions_telegram_date
ON transactions (telegram_id, tx_date DESC);

CREATE INDEX IF NOT EXISTS idx_users_telegram
ON users (telegram_id);
