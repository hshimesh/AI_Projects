"""
Database Explorer for MediBot Assignment
Explore the mediassist.db SQLite database
"""

import sqlite3
import pandas as pd
from pathlib import Path

# Path updated for learning folder location
DB_PATH = Path(__file__).parent.parent / "mediassist_data" / "db" / "mediassist.db"

# Connect to database
conn = sqlite3.connect(DB_PATH)

# Get all table names
tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", conn)

# Display all tables
for table_name in tables['name']:
    print("=" * 80)
    print(f"TABLE: {table_name}")
    print("=" * 80)
    df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
    print(df.to_string())
    print(f"\nTotal rows: {len(df)}\n")

conn.close()
