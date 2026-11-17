# WarungKu - Sprint 1 (US-1 sampai US-4)

Aplikasi web mobile-first (dibuka di browser HP atau laptop) dengan backend Python dan database SQLite.
Tidak perlu `pip install` apa pun, cukup Python 3.9 atau lebih baru.

## Menjalankan
```
python backend/server.py
```
- Laptop: http://localhost:8000
- HP (satu WiFi dengan laptop): alamat `http://<IP-laptop>:8000` yang tampil di terminal
- Akun awal: `pemilik` / `pemilik123` dan `kasir` / `kasir123` (ganti sebelum dipakai di kios sungguhan)

## Menjalankan tes otomatis (17 tes, satu per Acceptance Criteria)
```
python backend/test_api.py
```

## Peta fitur
| User story | Backend (backend/server.py) | Tampilan (app/index.html) |
|---|---|---|
| US-1 Akun terpisah | `login`, `logout`, hak akses per peran (`ROUTES`), `reports` | `loginView`, menu per peran di `appView` |
| US-2 Kelola barang | `list_products`, `create_product`, `update_product`, `delete_product` | `produkView`, `productForm` |
| US-3 Catat penjualan | `create_sale`, `sale_detail`, tabel `transactions` dan `transaction_items` | `kasirView`, `cartView`, `receipt` |
| US-4 Stok otomatis | pengurangan stok dan penolakan di dalam `create_sale` (satu transaksi database) | batas stok di `cartView` |

## Keputusan desain
- Harga dihitung ulang di server, bukan dipercaya dari aplikasi.
- Penjualan bersifat atomik: kalau satu barang stoknya kurang, tidak ada stok yang berkurang.
- Kasir tidak melihat harga beli. Harga beli dan harga jual disimpan pada tiap transaksi (dipakai laporan laba di US-10).
- Stok masih bisa diubah lewat form Ubah barang, sementara sampai US-5 (barang masuk) dan US-12 (stok opname) ada.
- Database `warungku.db` dibuat otomatis dan sudah masuk `.gitignore`.

## Belum termasuk (sprint berikutnya)
US-5 sampai US-14, mode offline, dan pembungkus aplikasi native.
