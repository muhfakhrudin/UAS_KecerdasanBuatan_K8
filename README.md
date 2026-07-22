# SmartPick — iPhone Second Recommendation System

Sistem rekomendasi iPhone bekas berbasis Django, menggunakan kombinasi TF-IDF, BM25, deteksi intent, dan value scoring untuk merekomendasikan listing terbaik dari dataset `data_iphone_v2.csv`.

## Requirement

- Python 3.11+ (proyek ini dibuat & diuji dengan Python 3.14)
- pip

## 1. Setup Virtual Environment

Proyek ini sudah menyertakan folder `.venv/`. Jika belum ada atau ingin membuat ulang:

```powershell
python -m venv .venv
```

Aktifkan virtual environment:

```powershell
# PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# Git Bash / WSL
source .venv/Scripts/activate
```

## 2. Install Dependencies

```bash
pip install -r requirements.txt
```

## 3. Migrasi Database

Database menggunakan SQLite (`db.sqlite3`, sudah tersedia di root proyek). Untuk memastikan skema terbaru sudah diterapkan:

```bash
python manage.py migrate
```

## 4. Load / Reload Dataset

Data listing iPhone di-import dari CSV ke database melalui management command `load_data`. Command ini juga melakukan preprocessing (parsing harga, normalisasi penyimpanan, imputasi battery health, deteksi kondisi, dsb).

```bash
python manage.py load_data
```

Secara default command membaca `data/data_iphone_v2.csv`. Untuk memakai file CSV lain:

```bash
python manage.py load_data --file path/ke/file.csv
```

## 5. Jalankan Server

```bash
python manage.py runserver
```

Buka browser ke [http://127.0.0.1:8000/](http://127.0.0.1:8000/) untuk mengakses wizard rekomendasi.

Halaman admin Django (untuk melihat/mengelola data listing) tersedia di [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/) — buat superuser terlebih dahulu jika diperlukan:

```bash
python manage.py createsuperuser
```

## Struktur Proyek

```
manage.py
requirements.txt
data/
  data_iphone_v2.csv       # dataset listing iPhone
core/                       # app utama (models, views, wizard, load_data command)
engine/                     # engine AI (TF-IDF, BM25, intent detection, value score, recommender)
templates/                  # template halaman (index, wizard, result)
smartpick/                  # konfigurasi proyek Django (settings, urls)
```

## Menjalankan Test

```bash
python manage.py test
```

atau untuk test khusus engine:

```bash
python engine/test_engine.py
```
