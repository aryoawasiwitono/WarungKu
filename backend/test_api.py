"""Tes otomatis Sprint 1 - satu tes per Acceptance Criteria. Jalankan: python test_api.py"""
import json, os, sys, tempfile, threading, unittest, urllib.error, urllib.request

os.environ["WARUNGKU_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server

PORT = 8765
URL = f"http://localhost:{PORT}"

def call(method, path, body=None, token=None):
    req = urllib.request.Request(URL + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())

class Sprint1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = server.make_server(PORT)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.owner = call("POST", "/api/login", {"username": "pemilik", "password": "pemilik123"})[1]["token"]
        cls.cashier = call("POST", "/api/login", {"username": "kasir", "password": "kasir123"})[1]["token"]

    @classmethod
    def tearDownClass(cls): cls.srv.shutdown()

    def product(self, name="Indomie", buy=2500, sell=3000, stock=10):
        s, d = call("POST", "/api/products", {"name": name, "buy_price": buy, "sell_price": sell, "stock": stock, "unit": "pcs"}, self.owner)
        self.assertEqual(s, 201); return d

    def stock(self, pid):
        return next(p["stock"] for p in call("GET", "/api/products", token=self.owner)[1] if p["id"] == pid)

    # ---- US-1
    def test_us1_pemilik_dan_kasir_bisa_login(self):
        for u, pw, role in (("pemilik", "pemilik123", "pemilik"), ("kasir", "kasir123", "kasir")):
            s, d = call("POST", "/api/login", {"username": u, "password": pw})
            self.assertEqual((s, d["user"]["role"]), (200, role))

    def test_us1_password_salah_ditolak_dengan_pesan(self):
        s, d = call("POST", "/api/login", {"username": "kasir", "password": "salah"})
        self.assertEqual(s, 401); self.assertEqual(d["error"], "Username atau password salah")

    def test_us1_kasir_tidak_bisa_laporan_dan_atur_harga(self):
        self.assertEqual(call("GET", "/api/reports", token=self.cashier)[0], 403)
        self.assertEqual(call("GET", "/api/reports", token=self.owner)[0], 200)
        p = self.product("Kopi")
        self.assertEqual(call("PUT", f"/api/products/{p['id']}", {"sell_price": 1}, self.cashier)[0], 403)
        self.assertEqual(call("POST", "/api/products", {"name": "X"}, self.cashier)[0], 403)

    def test_us1_tanpa_login_ditolak(self):
        self.assertEqual(call("GET", "/api/products")[0], 401)

    # ---- US-2
    def test_us2_tambah_produk_muncul_di_daftar(self):
        p = self.product("Teh Botol")
        self.assertIn(p["id"], [x["id"] for x in call("GET", "/api/products", token=self.owner)[1]])

    def test_us2_field_wajib(self):
        for bad in ({"name": "", "buy_price": 1, "sell_price": 2, "stock": 1}, {"name": "A", "sell_price": 2, "stock": 1},
                    {"name": "A", "buy_price": 1, "stock": 1}, {"name": "A", "buy_price": 1, "sell_price": 2},
                    {"name": "A", "buy_price": -1, "sell_price": 2, "stock": 1}):
            self.assertEqual(call("POST", "/api/products", bad, self.owner)[0], 400, bad)

    def test_us2_produk_berriwayat_hanya_bisa_dinonaktifkan(self):
        p = self.product("Gula")
        call("POST", "/api/sales", {"items": [{"product_id": p["id"], "qty": 1}], "paid": 5000}, self.cashier)
        s, d = call("DELETE", f"/api/products/{p['id']}", token=self.owner)
        self.assertEqual(s, 409)
        self.assertEqual(call("PUT", f"/api/products/{p['id']}", {"active": False}, self.owner)[1]["active"], False)
        self.assertNotIn(p["id"], [x["id"] for x in call("GET", "/api/products", token=self.cashier)[1]])

    def test_us2_produk_tanpa_riwayat_bisa_dihapus(self):
        p = self.product("Sementara")
        self.assertEqual(call("DELETE", f"/api/products/{p['id']}", token=self.owner)[0], 200)

    def test_us2_kasir_tidak_melihat_harga_beli(self):
        self.product("Rahasia")
        self.assertTrue(all("buy_price" not in x for x in call("GET", "/api/products", token=self.cashier)[1]))

    # ---- US-3
    def test_us3_beberapa_produk_total_kembalian_dan_detail(self):
        a, b = self.product("A", 1000, 2000, 10), self.product("B", 500, 1500, 10)
        s, d = call("POST", "/api/sales", {"items": [{"product_id": a["id"], "qty": 2}, {"product_id": b["id"], "qty": 3}], "paid": 10000}, self.cashier)
        self.assertEqual(s, 201)
        self.assertEqual((d["total"], d["paid"], d["change_amount"]), (8500, 10000, 1500))
        self.assertEqual((d["cashier_name"], len(d["items"])), ("Kasir", 2))
        self.assertRegex(d["created_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
        self.assertEqual(call("GET", f"/api/sales/{d['id']}", token=self.cashier)[1]["total"], 8500)

    def test_us3_uang_bayar_kurang_ditolak(self):
        p = self.product("C", 1, 5000, 5)
        s, d = call("POST", "/api/sales", {"items": [{"product_id": p["id"], "qty": 1}], "paid": 4000}, self.cashier)
        self.assertEqual(s, 400); self.assertEqual(self.stock(p["id"]), 5)

    def test_us3_keranjang_kosong_ditolak(self):
        self.assertEqual(call("POST", "/api/sales", {"items": [], "paid": 0}, self.cashier)[0], 400)

    def test_us3_harga_dihitung_server_bukan_dari_klien(self):
        p = self.product("D", 1, 7000, 5)
        s, d = call("POST", "/api/sales", {"items": [{"product_id": p["id"], "qty": 1, "sell_price": 1}], "paid": 7000}, self.cashier)
        self.assertEqual(d["total"], 7000)

    # ---- US-4
    def test_us4_stok_berkurang_setelah_transaksi(self):
        p = self.product("E", 1, 1000, 10)
        call("POST", "/api/sales", {"items": [{"product_id": p["id"], "qty": 4}], "paid": 4000}, self.cashier)
        self.assertEqual(self.stock(p["id"]), 6)

    def test_us4_melebihi_stok_ditolak_dan_stok_tidak_berubah(self):
        a, b = self.product("F", 1, 1000, 5), self.product("G", 1, 1000, 2)
        s, d = call("POST", "/api/sales", {"items": [{"product_id": a["id"], "qty": 3}, {"product_id": b["id"], "qty": 3}], "paid": 99999}, self.cashier)
        self.assertEqual(s, 409); self.assertIn("tidak cukup", d["error"])
        self.assertEqual((self.stock(a["id"]), self.stock(b["id"])), (5, 2))  # tidak ada yang berkurang (atomik)

    def test_us4_qty_sama_dengan_stok_boleh_lalu_stok_nol(self):
        p = self.product("H", 1, 1000, 3)
        self.assertEqual(call("POST", "/api/sales", {"items": [{"product_id": p["id"], "qty": 3}], "paid": 3000}, self.cashier)[0], 201)
        self.assertEqual(self.stock(p["id"]), 0)

    def test_us4_produk_nonaktif_tidak_bisa_dijual(self):
        p = self.product("I", 1, 1000, 3)
        call("PUT", f"/api/products/{p['id']}", {"active": False}, self.owner)
        self.assertEqual(call("POST", "/api/sales", {"items": [{"product_id": p["id"], "qty": 1}], "paid": 1000}, self.cashier)[0], 400)

if __name__ == "__main__":
    unittest.main(verbosity=2)
