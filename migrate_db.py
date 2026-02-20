import sqlite3
import os
from user_manager import UserManager

def migrate_database():
    db_path = 'users.db'
    
    if not os.path.exists(db_path):
        print("Database doesn't exist yet, creating fresh...")
        um = UserManager(db_path)
        print("Database created with new schema")
        return
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in c.fetchall()]
    
    if 'role' not in columns:
        print("Adding 'role' column to users table...")
        c.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
        conn.commit()
        print("Role column added successfully")
    else:
        print("Role column already exists")
    
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='order_invoices'")
    if not c.fetchone():
        print("Creating order_invoices table...")
        c.execute('''
            CREATE TABLE IF NOT EXISTS order_invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE NOT NULL,
                invoice_series TEXT NOT NULL,
                invoice_number TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        print("order_invoices table created successfully")
    else:
        print("order_invoices table already exists")
    
    conn.close()
    
    um = UserManager(db_path)
    
    c = sqlite3.connect(db_path).cursor()
    c.execute("SELECT id FROM users WHERE username = 'admin'")
    if not c.fetchone():
        print("Creating admin user...")
        success = um.create_user(
            username='admin',
            password='trendyol1',
            role='admin'
        )
        if success:
            print("Admin user created successfully (username: admin, password: trendyol1)")
        else:
            print("Failed to create admin user")
    else:
        print("Admin user already exists")
    
    print("\nMigration complete!")

if __name__ == '__main__':
    migrate_database()
