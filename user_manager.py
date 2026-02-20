import sqlite3
import os
from cryptography.fernet import Fernet
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, id, username, trendyol_api_key, trendyol_api_secret, 
                 trendyol_supplier_id, smartbill_api_token, smartbill_email, 
                 smartbill_company_cif, smartbill_gestiune=None, role='user'):
        self.id = id
        self.username = username
        self.trendyol_api_key = trendyol_api_key
        self.trendyol_api_secret = trendyol_api_secret
        self.trendyol_supplier_id = trendyol_supplier_id
        self.smartbill_api_token = smartbill_api_token
        self.smartbill_email = smartbill_email
        self.smartbill_company_cif = smartbill_company_cif
        self.smartbill_gestiune = smartbill_gestiune
        self.role = role
    
    def is_admin(self):
        return self.role == 'admin'

class UserManager:
    def __init__(self, db_path='users.db'):
        self.db_path = db_path
        encryption_key = os.getenv('ENCRYPTION_KEY')
        if not encryption_key:
            raise ValueError("ENCRYPTION_KEY environment variable must be set")
        self.cipher = Fernet(encryption_key.encode())
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                trendyol_api_key TEXT,
                trendyol_api_secret TEXT,
                trendyol_supplier_id TEXT,
                smartbill_api_token TEXT,
                smartbill_email TEXT,
                smartbill_company_cif TEXT,
                smartbill_gestiune TEXT,
                role TEXT DEFAULT 'user'
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS order_invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                order_id TEXT NOT NULL,
                invoice_series TEXT NOT NULL,
                invoice_number TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, order_id)
            )
        ''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_user_invoices ON order_invoices(user_id, order_id)')
        conn.commit()
        conn.close()
    
    def _hash_password(self, password):
        return generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)
    
    def _encrypt(self, value):
        if value is None:
            return None
        return self.cipher.encrypt(value.encode()).decode()
    
    def _decrypt(self, encrypted_value):
        if encrypted_value is None:
            return None
        return self.cipher.decrypt(encrypted_value.encode()).decode()
    
    def create_user(self, username, password, trendyol_api_key=None, 
                   trendyol_api_secret=None, trendyol_supplier_id=None,
                   smartbill_api_token=None, smartbill_email=None, 
                   smartbill_company_cif=None, smartbill_gestiune=None, role='user'):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        password_hash = self._hash_password(password)
        
        try:
            c.execute('''
                INSERT INTO users (username, password_hash, trendyol_api_key, 
                                 trendyol_api_secret, trendyol_supplier_id,
                                 smartbill_api_token, smartbill_email, 
                                 smartbill_company_cif, smartbill_gestiune, role)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                username,
                password_hash,
                self._encrypt(trendyol_api_key),
                self._encrypt(trendyol_api_secret),
                self._encrypt(trendyol_supplier_id),
                self._encrypt(smartbill_api_token),
                self._encrypt(smartbill_email),
                self._encrypt(smartbill_company_cif),
                self._encrypt(smartbill_gestiune),
                role
            ))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def authenticate_user(self, username, password):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''
            SELECT id, username, password_hash, trendyol_api_key, trendyol_api_secret, 
                   trendyol_supplier_id, smartbill_api_token, smartbill_email,
                   smartbill_company_cif, smartbill_gestiune, role
            FROM users 
            WHERE username = ?
        ''', (username,))
        
        row = c.fetchone()
        conn.close()
        
        if row and check_password_hash(row[2], password):
            return User(
                id=row[0],
                username=row[1],
                trendyol_api_key=self._decrypt(row[3]),
                trendyol_api_secret=self._decrypt(row[4]),
                trendyol_supplier_id=self._decrypt(row[5]),
                smartbill_api_token=self._decrypt(row[6]),
                smartbill_email=self._decrypt(row[7]),
                smartbill_company_cif=self._decrypt(row[8]),
                smartbill_gestiune=self._decrypt(row[9]),
                role=row[10] if len(row) > 10 and row[10] else 'user'
            )
        return None
    
    def get_user_by_id(self, user_id):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''
            SELECT id, username, trendyol_api_key, trendyol_api_secret, 
                   trendyol_supplier_id, smartbill_api_token, smartbill_email,
                   smartbill_company_cif, smartbill_gestiune, role
            FROM users 
            WHERE id = ?
        ''', (user_id,))
        
        row = c.fetchone()
        conn.close()
        
        if row:
            return User(
                id=row[0],
                username=row[1],
                trendyol_api_key=self._decrypt(row[2]),
                trendyol_api_secret=self._decrypt(row[3]),
                trendyol_supplier_id=self._decrypt(row[4]),
                smartbill_api_token=self._decrypt(row[5]),
                smartbill_email=self._decrypt(row[6]),
                smartbill_company_cif=self._decrypt(row[7]),
                smartbill_gestiune=self._decrypt(row[8]),
                role=row[9] if len(row) > 9 and row[9] else 'user'
            )
        return None
    
    def get_all_users(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''
            SELECT id, username, trendyol_api_key, trendyol_api_secret, 
                   trendyol_supplier_id, smartbill_api_token, smartbill_email,
                   smartbill_company_cif, smartbill_gestiune, role
            FROM users
        ''')
        
        rows = c.fetchall()
        conn.close()
        
        users = []
        for row in rows:
            users.append(User(
                id=row[0],
                username=row[1],
                trendyol_api_key=self._decrypt(row[2]),
                trendyol_api_secret=self._decrypt(row[3]),
                trendyol_supplier_id=self._decrypt(row[4]),
                smartbill_api_token=self._decrypt(row[5]),
                smartbill_email=self._decrypt(row[6]),
                smartbill_company_cif=self._decrypt(row[7]),
                smartbill_gestiune=self._decrypt(row[8]),
                role=row[9] if len(row) > 9 and row[9] else 'user'
            ))
        return users
    
    def update_user(self, user_id, username=None, password=None, trendyol_api_key=None,
                   trendyol_api_secret=None, trendyol_supplier_id=None,
                   smartbill_api_token=None, smartbill_email=None,
                   smartbill_company_cif=None, smartbill_gestiune=None, role=None):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        updates = []
        params = []
        
        if username is not None:
            updates.append("username = ?")
            params.append(username)
        if password is not None:
            updates.append("password_hash = ?")
            params.append(self._hash_password(password))
        if trendyol_api_key is not None:
            updates.append("trendyol_api_key = ?")
            params.append(self._encrypt(trendyol_api_key))
        if trendyol_api_secret is not None:
            updates.append("trendyol_api_secret = ?")
            params.append(self._encrypt(trendyol_api_secret))
        if trendyol_supplier_id is not None:
            updates.append("trendyol_supplier_id = ?")
            params.append(self._encrypt(trendyol_supplier_id))
        if smartbill_api_token is not None:
            updates.append("smartbill_api_token = ?")
            params.append(self._encrypt(smartbill_api_token))
        if smartbill_email is not None:
            updates.append("smartbill_email = ?")
            params.append(self._encrypt(smartbill_email))
        if smartbill_company_cif is not None:
            updates.append("smartbill_company_cif = ?")
            params.append(self._encrypt(smartbill_company_cif))
        if smartbill_gestiune is not None:
            updates.append("smartbill_gestiune = ?")
            params.append(self._encrypt(smartbill_gestiune))
        if role is not None:
            updates.append("role = ?")
            params.append(role)
        
        if not updates:
            return False
        
        params.append(user_id)
        query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
        
        try:
            c.execute(query, params)
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def delete_user(self, user_id):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        success = c.rowcount > 0
        conn.close()
        return success
