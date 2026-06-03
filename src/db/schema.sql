-- Cart Abandonment Intent Classifier — Postgres Schema
-- Run against your Railway Postgres instance:
--   psql $DATABASE_URL -f src/db/schema.sql

-- ── Sessions ──────────────────────────────────────────────────────────────────
-- Aggregated pixel event data per checkout session.
-- Populated by POST /webhook/session-event, consumed during classification.

CREATE TABLE IF NOT EXISTS sessions (
    id                        SERIAL PRIMARY KEY,
    session_id                TEXT NOT NULL UNIQUE,  -- Shopify checkout token
    customer_id               TEXT,
    shop_id                   TEXT,                  -- for multi-tenant Phase 6
    visited_return_policy     BOOLEAN DEFAULT FALSE,
    visited_shipping_info     BOOLEAN DEFAULT FALSE,
    checkout_start_time       BIGINT,                -- Unix timestamp
    time_on_checkout_seconds  INT,
    items_added_and_removed   INT DEFAULT 0,
    page_views                JSONB DEFAULT '[]',    -- array of URLs visited
    raw_events                JSONB DEFAULT '[]',    -- full event log for debugging
    created_at                TIMESTAMPTZ DEFAULT NOW(),
    updated_at                TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_customer_id ON sessions (customer_id);
CREATE INDEX IF NOT EXISTS idx_sessions_session_id  ON sessions (session_id);


-- ── Classifications ───────────────────────────────────────────────────────────
-- One row per classification result. Append-only — never update or delete.

CREATE TABLE IF NOT EXISTS classifications (
    id                  SERIAL PRIMARY KEY,
    customer_id         TEXT NOT NULL,
    shop_id             TEXT,
    email               TEXT,
    session_id          TEXT,

    -- Classification result
    intent              TEXT NOT NULL CHECK (intent IN (
                            'price_sensitive',
                            'trust_gap',
                            'distracted',
                            'research_phase'
                        )),
    confidence          FLOAT NOT NULL,
    klaviyo_flow        TEXT NOT NULL,
    reasoning           TEXT,

    -- Input snapshot (for debugging + model improvement)
    profile_snapshot    JSONB,                       -- full profile sent to Claude

    -- Outcome tracking (updated later via /feedback endpoint — Phase 2+)
    klaviyo_updated     BOOLEAN DEFAULT FALSE,
    flow_triggered      BOOLEAN DEFAULT FALSE,
    converted           BOOLEAN,                     -- did they complete purchase?
    conversion_value    FLOAT,

    -- Performance
    latency_ms          INT,
    claude_model        TEXT,

    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_classifications_customer_id ON classifications (customer_id);
CREATE INDEX IF NOT EXISTS idx_classifications_intent      ON classifications (intent);
CREATE INDEX IF NOT EXISTS idx_classifications_created_at  ON classifications (created_at);


-- ── Failed classifications ────────────────────────────────────────────────────
-- Retry queue for classification attempts that failed (API error, timeout, etc.)

CREATE TABLE IF NOT EXISTS failed_classifications (
    id              SERIAL PRIMARY KEY,
    customer_id     TEXT NOT NULL,
    shop_id         TEXT,
    session_id      TEXT,
    profile_snapshot JSONB,                          -- profile at time of failure
    error_message   TEXT,
    attempt_count   INT DEFAULT 1,
    last_attempted  TIMESTAMPTZ DEFAULT NOW(),
    resolved        BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_failed_customer_id ON failed_classifications (customer_id);
CREATE INDEX IF NOT EXISTS idx_failed_resolved    ON failed_classifications (resolved);


-- ── Workspaces (Phase 6 — multi-tenant) ──────────────────────────────────────
-- One row per installed Shopify store.

CREATE TABLE IF NOT EXISTS workspaces (
    id                  SERIAL PRIMARY KEY,
    shop_id             TEXT NOT NULL UNIQUE,        -- e.g. my-store.myshopify.com
    shopify_access_token TEXT,                       -- encrypted at rest
    klaviyo_private_key  TEXT,                       -- encrypted at rest
    config              JSONB,                       -- per-store config overrides
    onboarding_complete BOOLEAN DEFAULT FALSE,
    installed_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
