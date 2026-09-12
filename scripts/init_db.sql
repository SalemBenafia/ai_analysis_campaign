-- InsightAI initialization script
-- Runs once when PostgreSQL container is first created.
-- Alembic handles the full schema migration; this only sets extensions.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
