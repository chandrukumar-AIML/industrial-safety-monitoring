-- docker/init-db.sql
-- Runs once when PostgreSQL container first starts.
-- Creates additional databases needed by MLflow.

-- MLflow needs its own database
CREATE DATABASE mlflow_runs;
GRANT ALL PRIVILEGES ON DATABASE mlflow_runs TO safety;

-- Ensure safety_monitor DB is owned by safety user (already created by POSTGRES_DB env)
GRANT ALL PRIVILEGES ON DATABASE safety_monitor TO safety;
