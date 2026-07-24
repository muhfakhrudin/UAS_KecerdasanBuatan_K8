# iRecom Master — Sistem Rekomendasi iPhone Bekas

Aplikasi web berbasis Django yang merekomendasikan iPhone bekas dari dataset listing Tokopedia. Pengguna menjawab wizard 9 langkah tentang preferensinya (seri, varian, budget, penyimpanan, battery health, kondisi, garansi, dan prioritas utama), lalu sistem menyaring listing yang cocok dan mengurutkannya memakai kombinasi BM25 (relevansi teks) dan ValueScore (skor preferensi berbobot adaptif, dengan bantuan fuzzy logic untuk battery health, efisiensi harga, dan trust score toko).

## Requirement

- Python 3.11+ (dibuat & diuji dengan Python 3.14)
- pip

## 1. Clone / Salin Proyek

```bash
git clone <url-repo>
cd "UAS"
```

## 2. Buat & Aktifkan Virtual Environment

```bash
python -m venv .venv
```

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# Git Bash / WSL / Linux / macOS
source .venv/Scripts/activate   # Windows Git Bash
# atau
source .venv/bin/activate       # Linux / macOS
```

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

Paket utama yang dipakai: `django`, `pandas`, `scikit-learn` (TF-IDF), `rank-bm25` (BM25), `nltk`, `numpy`, `python-dotenv`, `whitenoise`.

## 4. Migrasi Database

Proyek memakai SQLite (`db.sqlite3`). Jalankan migrasi untuk memastikan skema terbaru sudah diterapkan:

```bash
python manage.py migrate
```

## 5. Load / Reload Dataset

Data listing iPhone diimpor dari CSV ke database melalui management command `load_data`, yang juga menjalankan seluruh tahap preprocessing (parsing harga, normalisasi penyimpanan, ekstraksi kondisi & garansi, imputasi battery health bertingkat, perhitungan trust score, dan penyusunan dokumen teks untuk indeks BM25).

```bash
python manage.py load_data
```

Secara default command membaca `data/data_iphone_v2.csv`. Untuk memakai file CSV lain:

```bash
python manage.py load_data --file path/ke/file.csv
```

## 6. Jalankan Server

```bash
python manage.py runserver
```

Buka browser ke [http://127.0.0.1:8000/](http://127.0.0.1:8000/) untuk mengakses wizard rekomendasi. Tersedia mode gelap (tombol ikon matahari/bulan di header).

Halaman admin Django (untuk melihat/mengelola data listing) tersedia di [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/) — buat superuser terlebih dahulu jika diperlukan:

```bash
python manage.py createsuperuser
```

## Struktur Proyek

```
manage.py
requirements.txt
data/
  data_iphone_v2.csv          # dataset listing iPhone bekas
core/                          # app utama: model data, view wizard, command load_data
  management/commands/
    load_data.py                # import + preprocessing dataset
    algorithm_breakdown.py       # tampilkan breakdown skor tiap tahap algoritma untuk satu query
    weight_sensitivity.py        # uji sensitivitas bobot BM25/ValueScore
engine/                         # engine AI
  tfidf_engine.py                # perhitungan TF-IDF & cosine similarity
  bm25_engine.py                  # indexing & scoring BM25 (rank_bm25)
  intent_detector.py              # deteksi mode spec_first / budget_first dari kueri bebas
  fuzzy_engine.py                  # Fuzzy Inference System (Mamdani) untuk FuzzyQuality
  value_score.py                   # kombinasi fuzzy + bobot adaptif -> ValueScore
  recommender.py                    # orkestrasi: hard filter -> BM25 + ValueScore -> top 3
templates/                     # halaman: index, wizard (9 langkah), result
smartpick/                      # konfigurasi proyek Django (settings, urls)
```

## Menjalankan Test

```bash
python manage.py test
```

Atau untuk pengujian khusus modul engine:

```bash
python engine/test_engine.py
```

## Perkakas Analisis Tambahan

```bash
# Breakdown skor (TF-IDF, BM25, fuzzy, ValueScore) untuk satu skenario query
python manage.py algorithm_breakdown

# Uji sensitivitas bobot FinalScore terhadap perubahan alpha (BM25 vs ValueScore)
python manage.py weight_sensitivity
```

## Troubleshooting

| Masalah | Solusi |
|---|---|
| `ModuleNotFoundError` saat runserver | Pastikan virtual environment sudah aktif dan `pip install -r requirements.txt` sudah selesai tanpa error |
| Wizard/hasil kosong atau error "listing tidak ditemukan" | Jalankan ulang `python manage.py load_data` untuk memastikan database terisi |
| Perubahan pada `data_iphone_v2.csv` tidak muncul di aplikasi | Data hanya dimuat ulang saat `load_data` dijalankan manual, jalankan kembali setelah mengubah CSV |
| Port 8000 sudah dipakai | Jalankan `python manage.py runserver 8001` (atau port lain) |
