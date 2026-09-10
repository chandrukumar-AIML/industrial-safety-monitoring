"""
scripts/create_admin.py

Bootstrap the first admin user in the database.

Usage:
    python scripts/create_admin.py --email admin@yourcompany.com --password YourSecurePass123
    python scripts/create_admin.py  # uses env vars ADMIN_EMAIL / ADMIN_PASSWORD

Set env vars before running:
    DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
    JWT_SECRET=your-secret-key
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.auth.jwt_utils import hash_password


async def create_admin(email: str, password: str, full_name: str, org_id: str):
    db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./safety_monitor.db")
    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        # Check if user already exists
        result = await conn.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": email.lower().strip()},
        )
        existing = result.fetchone()
        if existing:
            print(f"User {email} already exists (id={existing[0]}). Skipping.")
            return

        hashed = hash_password(password)
        await conn.execute(
            text("""
                INSERT INTO users (email, hashed_password, full_name, role, org_id, is_active)
                VALUES (:email, :pw, :name, 'admin', :org_id, TRUE)
            """),
            {
                "email": email.lower().strip(),
                "pw": hashed,
                "name": full_name,
                "org_id": org_id,
            },
        )
    print(f"Admin user created: {email} | role=admin | org={org_id}")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create the first admin user")
    parser.add_argument("--email", default=os.getenv("ADMIN_EMAIL", "admin@safeguardai.io"))
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD", ""))
    parser.add_argument("--name", default=os.getenv("ADMIN_NAME", "Admin"))
    parser.add_argument("--org", default=os.getenv("ADMIN_ORG", "default"))
    args = parser.parse_args()

    if not args.password:
        print("ERROR: --password is required (or set ADMIN_PASSWORD env var)")
        sys.exit(1)

    asyncio.run(create_admin(args.email, args.password, args.name, args.org))
