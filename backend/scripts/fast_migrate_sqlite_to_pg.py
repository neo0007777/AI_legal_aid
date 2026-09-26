#!/usr/bin/env python3
"""
Fast bulk migration of SQLite data to PostgreSQL using execute_values.
Syncs all existing rows (provisions, acts, users, ingestion_logs, mappings) in batch.
"""
import os
import sqlite3
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

pg_url = os.getenv("DATABASE_URL")
if pg_url.startswith("postgres://"):
    pg_url = pg_url.replace("postgres://", "postgresql://", 1)

sqlite_path = os.path.join(os.path.dirname(__file__), "..", "nyayasetu.db")
if not os.path.exists(sqlite_path):
    print("No local nyayasetu.db found.")
    exit(0)

sqlite_conn = sqlite3.connect(sqlite_path)
sqlite_cur = sqlite_conn.cursor()

pg_conn = psycopg2.connect(pg_url)
pg_cur = pg_conn.cursor()

tables = [
    "users",
    "acts",
    "provisions",
    "statute_mappings",
    "ingestion_logs",
    "corrections",
    "search_cache",
    "workflows",
    "tasks",
    "compliance_alerts"
]

print("Starting fast bulk migration...")

for table in tables:
    try:
        sqlite_cur.execute(f"PRAGMA table_info({table})")
        columns_info = sqlite_cur.fetchall()
        if not columns_info:
            continue
        
        col_names = [c[1] for c in columns_info]
        bool_cols = {c[1] for c in columns_info if "bool" in c[2].lower()}
        
        sqlite_cur.execute(f"SELECT * FROM {table}")
        raw_rows = sqlite_cur.fetchall()
        if not raw_rows:
            continue
        
        # Transform boolean ints to booleans if any
        converted_rows = []
        for row in raw_rows:
            row_list = list(row)
            for idx, col in enumerate(col_names):
                if col in bool_cols and row_list[idx] is not None:
                    row_list[idx] = bool(row_list[idx])
            converted_rows.append(tuple(row_list))
        
        col_str = ", ".join([f'"{c}"' for c in col_names])
        query = f'INSERT INTO {table} ({col_str}) VALUES %s ON CONFLICT (id) DO NOTHING;'
        
        execute_values(pg_cur, query, converted_rows, page_size=200)
        pg_conn.commit()
        print(f"  ✓ {table}: successfully bulk migrated {len(converted_rows)} rows.")
    except Exception as e:
        pg_conn.rollback()
        print(f"  ✗ {table} failed: {e}")

print("\n--- Row counts in PostgreSQL ---")
for table in tables:
    try:
        pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
        cnt = pg_cur.fetchone()[0]
        print(f"  {table}: {cnt}")
    except Exception as e:
        print(f"  {table}: {e}")

sqlite_conn.close()
pg_conn.close()
print("Fast migration finished successfully!")
