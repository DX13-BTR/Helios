-- Create schemas if missing
CREATE SCHEMA IF NOT EXISTS helios;
CREATE SCHEMA IF NOT EXISTS legacy;

-- === 1) triaged tasks (used by /api/triaged-tasks and fixed-date join) ===
-- Expected columns: id, name, due_date, priority, score, status
DROP VIEW IF EXISTS helios.triaged_tasks;
CREATE VIEW helios.triaged_tasks AS
SELECT
  NULL::uuid          AS id,
  ''::text            AS name,
  NOW()::timestamptz  AS due_date,
  'normal'::text      AS priority,
  0.0::numeric        AS score,
  'open'::text        AS status
WHERE FALSE;

-- === 2) Financial snapshot summary (legacy.fss_summary) ===
DROP VIEW IF EXISTS legacy.fss_summary;
CREATE VIEW legacy.fss_summary AS
SELECT
  NULL::uuid         AS id,
  NOW()::timestamptz AS period_start,
  NOW()::timestamptz AS period_end,
  0::numeric         AS total_cash,
  0::numeric         AS projected_cash_30d,
  0::numeric         AS projected_cash_60d,
  0::integer         AS runway_days,
  NOW()::timestamptz AS created_at
WHERE FALSE;

-- === 3) Financial advice (legacy.fss_advice) ===
DROP VIEW IF EXISTS legacy.fss_advice;
CREATE VIEW legacy.fss_advice AS
SELECT
  NULL::uuid         AS id,
  NULL::uuid         AS summary_id,
  ''::text           AS kind,
  ''::text           AS message,
  NOW()::timestamptz AS created_at
WHERE FALSE;

-- === 4) Balances (legacy.balances) ===
-- Expected: account_id, account_name, balance, as_of (code uses DISTINCT ON)
DROP VIEW IF EXISTS legacy.balances;
CREATE VIEW legacy.balances AS
SELECT
  ''::text           AS account_id,
  ''::text           AS account_name,
  0::numeric         AS balance,
  NOW()::timestamptz AS as_of
WHERE FALSE;
