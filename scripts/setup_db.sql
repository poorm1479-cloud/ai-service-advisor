-- Create local role + database for Phase 0
-- Run as a Postgres superuser, e.g.:
--   psql -U postgres -f scripts/setup_db.sql

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'asa') THEN
    CREATE ROLE asa LOGIN PASSWORD 'asa';
  END IF;
END
$$;

SELECT 'CREATE DATABASE ai_service_advisor OWNER asa'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'ai_service_advisor')\gexec

GRANT ALL PRIVILEGES ON DATABASE ai_service_advisor TO asa;

\c ai_service_advisor

GRANT ALL ON SCHEMA public TO asa;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO asa;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO asa;
