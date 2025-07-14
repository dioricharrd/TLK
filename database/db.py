import pymysql

# Konfigurasi koneksi langsung ke database lokal
CONFIG = {
    'host': 'localhost',          # atau 127.0.0.1
    'user': 'root',               # ganti dengan user DB kamu
    'password': '',               # ganti dengan password DB kamu
    'db': 'tlkm',                 # nama database
    'cursorclass': pymysql.cursors.DictCursor
}

def get_connection_database():
    return pymysql.connect(**CONFIG)
