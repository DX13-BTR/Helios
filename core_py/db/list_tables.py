import sqlite3

# Path to your SQLite database
db_path = "helios.db"  # Change if needed

# Connect to the database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get list of all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

# Print each table name
print("Tables in the database:")
for table in tables:
    print(f"- {table[0]}")

# Close the connection
conn.close()
