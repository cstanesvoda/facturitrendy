import sqlite3

conn = sqlite3.connect('users.db')
c = conn.cursor()

try:
    c.execute('ALTER TABLE users ADD COLUMN smartbill_gestiune TEXT')
    conn.commit()
    print("Successfully added smartbill_gestiune column to users table")
except sqlite3.OperationalError as e:
    if 'duplicate column name' in str(e).lower():
        print("Column smartbill_gestiune already exists")
    else:
        print(f"Error: {e}")
finally:
    conn.close()
