import sqlite3

conn = sqlite3.connect('documents.db')
cursor = conn.cursor()

# Get table schema
cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='documents'")
schema = cursor.fetchone()

if schema:
    print("✅ Documents table exists")
    print("\nSchema:")
    print(schema[0])
    
    # Get column info
    cursor.execute("PRAGMA table_info(documents)")
    columns = cursor.fetchall()
    print("\nColumns:")
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")
else:
    print("❌ Table not found")

conn.close()
