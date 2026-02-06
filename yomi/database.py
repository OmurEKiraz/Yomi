import sqlite3
import os
import logging

class YomiDB:
    def __init__(self, db_path):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._init_db()

    def _init_db(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS downloads (
                manga TEXT,
                chapter TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (manga, chapter)
            )
        ''')
        self.conn.commit()

    def _normalize(self, text):
        """Metni standart hale getirir (Boşlukları sil, küçük harf yap)."""
        if not text: return ""
        # "Chapter 01" -> "chapter1", "Vol. 1" -> "vol1"
        return "".join(text.lower().split())

    def is_completed(self, manga, chapter):
        """Bölüm daha önce indirilmiş mi kontrol eder."""
        m_norm = self._normalize(manga)
        c_norm = self._normalize(chapter)
        
        # Tam eşleşme veya normalize edilmiş eşleşme ara
        self.cursor.execute('SELECT 1 FROM downloads WHERE manga = ? AND chapter = ?', (manga, chapter))
        if self.cursor.fetchone(): return True
        
        # Eğer tam eşleşme yoksa, veritabanındaki tüm kayıtları çekip normalize ederek karşılaştır (Biraz yavaş ama kesin)
        self.cursor.execute('SELECT chapter FROM downloads WHERE manga = ?', (manga,))
        results = self.cursor.fetchall()
        for (saved_chap,) in results:
            if self._normalize(saved_chap) == c_norm:
                return True
        return False

    def mark_completed(self, manga, chapter):
        """Bölümü tamamlandı olarak işaretler."""
        try:
            self.cursor.execute('INSERT OR REPLACE INTO downloads (manga, chapter) VALUES (?, ?)', (manga, chapter))
            self.conn.commit()
        except Exception as e:
            logging.error(f"DB Error: {e}")

    def close(self):
        self.conn.close()