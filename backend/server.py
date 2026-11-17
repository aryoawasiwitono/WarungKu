#!/usr/bin/env python3
"""WarungKu - backend Sprint 1 (US-1 sampai US-4).
Hanya memakai library standar Python. Jalankan: python server.py
"""
import hashlib, json, os, re, secrets, socket, sqlite3, traceback
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("WARUNGKU_DB", os.path.join(BASE, "warungku.db"))
INDEX = os.path.join(BASE, "..", "app", "index.html")
SESSION_HOURS = 12

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('pemilik','kasir')), salt TEXT NOT NULL, pw_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT NOT NULL,
  buy_price INTEGER NOT NULL CHECK(buy_price>=0), sell_price INTEGER NOT NULL CHECK(sell_price>=0),
  unit TEXT NOT NULL DEFAULT 'pcs', stock INTEGER NOT NULL DEFAULT 0 CHECK(stock>=0), active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, cashier_id INTEGER NOT NULL,
  cashier_name TEXT NOT NULL, total INTEGER NOT NULL, paid INTEGER NOT NULL, change_amount INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS transaction_items(id INTEGER PRIMARY KEY, transaction_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
  name TEXT NOT NULL, qty INTEGER NOT NULL, buy_price INTEGER NOT NULL, sell_price INTEGER NOT NULL);
"""

class ApiError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg); self.code, self.msg = code, msg

def db():
    c = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    c.row_factory = sqlite3.Row
    return c

def hash_pw(pw, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), 120_000).hex()

def add_user(c, username, name, role, pw):
    salt = secrets.token_hex(16)
    c.execute("INSERT INTO users(username,name,role,salt,pw_hash) VALUES(?,?,?,?,?)", (username, name, role, salt, hash_pw(pw, salt)))

def init_db():
    c = db(); c.executescript(SCHEMA)
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:  # akun awal (US-1), GANTI password sebelum dipakai sungguhan
        add_user(c, "pemilik", "Pemilik Kios", "pemilik", "pemilik123")
        add_user(c, "kasir", "Kasir", "kasir", "kasir123")
    c.close()

def to_int(v, label):
    if isinstance(v, bool) or v is None or (isinstance(v, str) and not re.fullmatch(r"\d+", v.strip())) or not isinstance(v, (int, str)):
        raise ApiError(400, f"{label} wajib diisi berupa angka 0 atau lebih")
    n = int(v)
    if n < 0: raise ApiError(400, f"{label} tidak boleh negatif")
    return n

def pub_product(r, role):
    d = dict(r); d["active"] = bool(d["active"])
    if role != "pemilik": d.pop("buy_price")  # harga beli rahasia pemilik
    return d

# ---------- handler endpoint: (conn, user, params, query, body) -> (kode, data) ----------
def login(c, u, p, q, b):  # US-1
    row = c.execute("SELECT * FROM users WHERE username=?", (str(b.get("username", "")).strip(),)).fetchone()
    ok = row and secrets.compare_digest(hash_pw(str(b.get("password", "")), row["salt"]), row["pw_hash"])
    if not ok: raise ApiError(401, "Username atau password salah")
    token = secrets.token_urlsafe(32)
    exp = (datetime.now() + timedelta(hours=SESSION_HOURS)).isoformat()
    c.execute("INSERT INTO sessions VALUES(?,?,?)", (token, row["id"], exp))
    return 200, {"token": token, "user": {"id": row["id"], "username": row["username"], "name": row["name"], "role": row["role"]}}

def logout(c, u, p, q, b):
    c.execute("DELETE FROM sessions WHERE token=?", (u["token"],)); return 200, {"ok": True}

def me(c, u, p, q, b): return 200, {k: u[k] for k in ("id", "username", "name", "role")}

def reports(c, u, p, q, b): return 200, {"message": "Laporan tersedia mulai Sprint 2"}  # kerangka akses pemilik (US-1)

def list_products(c, u, p, q, b):  # US-2
    sql, args = "SELECT * FROM products WHERE 1=1", []
    if u["role"] != "pemilik": sql += " AND active=1"
    term = (q.get("q") or [""])[0].strip()
    if term: sql += " AND name LIKE ?"; args.append(f"%{term}%")
    rows = c.execute(sql + " ORDER BY name COLLATE NOCASE", args).fetchall()
    return 200, [pub_product(r, u["role"]) for r in rows]

def create_product(c, u, p, q, b):
    name = str(b.get("name") or "").strip()
    if not name: raise ApiError(400, "Nama barang wajib diisi")
    buy, sell = to_int(b.get("buy_price"), "Harga beli"), to_int(b.get("sell_price"), "Harga jual")
    stock = to_int(b.get("stock"), "Stok awal")
    unit = str(b.get("unit") or "pcs").strip() or "pcs"
    cur = c.execute("INSERT INTO products(name,buy_price,sell_price,unit,stock) VALUES(?,?,?,?,?)", (name, buy, sell, unit, stock))
    return 201, pub_product(c.execute("SELECT * FROM products WHERE id=?", (cur.lastrowid,)).fetchone(), "pemilik")

def update_product(c, u, p, q, b):
    row = c.execute("SELECT * FROM products WHERE id=?", (p["id"],)).fetchone()
    if not row: raise ApiError(404, "Barang tidak ditemukan")
    name = str(b.get("name", row["name"])).strip()
    if not name: raise ApiError(400, "Nama barang wajib diisi")
    buy = to_int(b.get("buy_price", row["buy_price"]), "Harga beli")
    sell = to_int(b.get("sell_price", row["sell_price"]), "Harga jual")
    stock = to_int(b.get("stock", row["stock"]), "Stok")  # sementara boleh diubah sampai ada US-5 dan US-12
    unit = str(b.get("unit", row["unit"])).strip() or "pcs"
    active = 1 if b.get("active", bool(row["active"])) else 0
    c.execute("UPDATE products SET name=?,buy_price=?,sell_price=?,unit=?,stock=?,active=? WHERE id=?", (name, buy, sell, unit, stock, active, row["id"]))
    return 200, pub_product(c.execute("SELECT * FROM products WHERE id=?", (row["id"],)).fetchone(), "pemilik")

def delete_product(c, u, p, q, b):
    if not c.execute("SELECT 1 FROM products WHERE id=?", (p["id"],)).fetchone(): raise ApiError(404, "Barang tidak ditemukan")
    if c.execute("SELECT 1 FROM transaction_items WHERE product_id=? LIMIT 1", (p["id"],)).fetchone():
        raise ApiError(409, "Barang sudah punya riwayat transaksi, hanya bisa dinonaktifkan")
    c.execute("DELETE FROM products WHERE id=?", (p["id"],)); return 200, {"ok": True}

def get_sale(c, tid):
    t = c.execute("SELECT * FROM transactions WHERE id=?", (tid,)).fetchone()
    if not t: raise ApiError(404, "Transaksi tidak ditemukan")
    d = dict(t); d["items"] = [dict(r) for r in c.execute("SELECT product_id,name,qty,sell_price FROM transaction_items WHERE transaction_id=?", (tid,))]
    return d

def create_sale(c, u, p, q, b):  # US-3 dan US-4
    items, merged = b.get("items"), {}
    if not isinstance(items, list) or not items: raise ApiError(400, "Keranjang masih kosong")
    paid = to_int(b.get("paid"), "Uang bayar")
    for it in items:
        pid, qty = to_int(it.get("product_id"), "Barang"), to_int(it.get("qty"), "Jumlah")
        if qty < 1: raise ApiError(400, "Jumlah minimal 1")
        merged[pid] = merged.get(pid, 0) + qty
    c.execute("BEGIN IMMEDIATE")  # satu transaksi database: semua tersimpan atau tidak sama sekali
    try:
        lines, total = [], 0
        for pid, qty in merged.items():
            r = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            if not r or not r["active"]: raise ApiError(400, "Ada barang yang tidak tersedia, muat ulang daftar barang")
            if qty > r["stock"]: raise ApiError(409, f"Stok {r['name']} tidak cukup (tersisa {r['stock']} {r['unit']})")
            lines.append((r, qty)); total += r["sell_price"] * qty
        if paid < total: raise ApiError(400, f"Uang bayar kurang Rp {total - paid:,}".replace(",", "."))
        cur = c.execute("INSERT INTO transactions(created_at,cashier_id,cashier_name,total,paid,change_amount) VALUES(?,?,?,?,?,?)",
                        (datetime.now().isoformat(timespec="seconds"), u["id"], u["name"], total, paid, paid - total))
        for r, qty in lines:
            c.execute("INSERT INTO transaction_items(transaction_id,product_id,name,qty,buy_price,sell_price) VALUES(?,?,?,?,?,?)",
                      (cur.lastrowid, r["id"], r["name"], qty, r["buy_price"], r["sell_price"]))
            c.execute("UPDATE products SET stock=stock-? WHERE id=?", (qty, r["id"]))  # US-4
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK"); raise
    return 201, get_sale(c, cur.lastrowid)

def sale_detail(c, u, p, q, b):
    d = get_sale(c, int(p["id"]))
    if u["role"] != "pemilik" and d["cashier_id"] != u["id"]: raise ApiError(403, "Akses ditolak")
    return 200, d

# (metode, pola, fungsi, akses) akses: None=publik, "any"=sudah login, "pemilik"=khusus pemilik
ROUTES = [
    ("POST", r"/api/login", login, None), ("POST", r"/api/logout", logout, "any"), ("GET", r"/api/me", me, "any"),
    ("GET", r"/api/reports", reports, "pemilik"),
    ("GET", r"/api/products", list_products, "any"), ("POST", r"/api/products", create_product, "pemilik"),
    ("PUT", r"/api/products/(?P<id>\d+)", update_product, "pemilik"), ("DELETE", r"/api/products/(?P<id>\d+)", delete_product, "pemilik"),
    ("POST", r"/api/sales", create_sale, "any"), ("GET", r"/api/sales/(?P<id>\d+)", sale_detail, "any"),
]

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a): pass

    def reply(self, code, data, ctype="application/json; charset=utf-8"):
        raw = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def handle_any(self, method):
        path, query = urlparse(self.path).path, parse_qs(urlparse(self.path).query)
        if method == "GET" and path in ("/", "/index.html"):
            with open(INDEX, "rb") as f: return self.reply(200, f.read(), "text/html; charset=utf-8")
        c = None
        try:
            for m, pat, fn, access in ROUTES:
                mt = re.fullmatch(pat, path)
                if m != method or not mt: continue
                c = db(); user = None
                if access:
                    tok = self.headers.get("Authorization", "")[7:]
                    row = c.execute("SELECT u.*, s.token, s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?", (tok,)).fetchone() if tok else None
                    if not row or row["expires_at"] < datetime.now().isoformat(): raise ApiError(401, "Silakan login terlebih dahulu")
                    user = dict(row)
                    if access == "pemilik" and user["role"] != "pemilik": raise ApiError(403, "Akses ditolak: hanya untuk pemilik")
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(n) or b"{}") if n else {}
                    if not isinstance(body, dict): raise ValueError
                except ValueError: raise ApiError(400, "Format data tidak valid")
                code, data = fn(c, user, mt.groupdict(), query, body)
                return self.reply(code, data)
            raise ApiError(404, "Halaman tidak ditemukan")
        except ApiError as e: self.reply(e.code, {"error": e.msg})
        except Exception: traceback.print_exc(); self.reply(500, {"error": "Terjadi kesalahan pada server"})
        finally:
            if c: c.close()

    def do_GET(self): self.handle_any("GET")
    def do_POST(self): self.handle_any("POST")
    def do_PUT(self): self.handle_any("PUT")
    def do_DELETE(self): self.handle_any("DELETE")

def make_server(port=8000):
    init_db(); return ThreadingHTTPServer(("0.0.0.0", port), Handler)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    srv = make_server(port)
    try: ip = socket.gethostbyname(socket.gethostname())
    except OSError: ip = "IP-laptop"
    print(f"WarungKu berjalan.\n  Laptop : http://localhost:{port}\n  HP     : http://{ip}:{port} (satu WiFi)\n  Akun   : pemilik/pemilik123 , kasir/kasir123\nTekan Ctrl+C untuk berhenti.")
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\nBerhenti.")
