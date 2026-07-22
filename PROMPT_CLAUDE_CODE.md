# PROMPT UNTUK CLAUDE CODE (VS CODE AGENT)
# Copy seluruh isi file ini dan paste ke Claude Code

---

## KONTEKS PROYEK

Kamu adalah senior Python developer yang akan membangun sistem rekomendasi iPhone bekas (second) berbasis AI menggunakan Django. Ini adalah proyek UTS Machine Learning yang akan dipamerkan, jadi UI harus terlihat profesional dan sistem harus benar-benar bekerja sebagai recommendation system, bukan sekadar search engine.

**Nama proyek:** SmartPick — iPhone Second Recommendation System  
**Stack:** Django 5, Python 3.11+, SQLite (development), scikit-learn, rank_bm25, NLTK  
**Dataset:** `data_iphone_v2.csv` (723 listing, sudah tersedia di folder proyek)

---

## STRUKTUR DATASET

File CSV memiliki kolom berikut:
```
Platform, Nama Toko, Rating Produk, Produk Terjual, Kategori Seri,
Kategori Varian, penyimpanan, Battery Health, Harga, Wilayah Toko, Link Pembelian
```

**Contoh data:**
```
Tokopedia, Wonderland Store, 5.0, 40, iPhone 11 Series, iPhone 11 Pro, 256GB, N/A, Rp9.000.000, Surabaya, https://tokopedia.com/...
Tokopedia, Cyrus Cell BEC, 5.0, 23, iPhone 11 Series, iPhone 11 Pro Max, 64GB, 85, Rp6.165.000, Bandung, https://tokopedia.com/...
```

**Masalah data yang harus ditangani:**
- Battery Health: 72.6% bernilai N/A atau kosong → gunakan imputasi median per varian
- Harga format string "Rp9.000.000" → harus dikonversi ke integer
- Penyimpanan tidak konsisten: "126GB" → "128GB", "1000GB" → "1TB" → normalisasi
- Rating 0.0 → artinya belum ada review, bukan rating buruk → buat flag `has_rating`
- Tidak ada kolom kondisi fisik → extract dari nama produk menggunakan keyword matching

---

## YANG HARUS DIBANGUN

### TASK 1 — Setup Django Project

Buat struktur proyek Django berikut:
```
smartpick/
├── manage.py
├── requirements.txt
├── data/
│   └── data_iphone_v2.csv        ← taruh dataset di sini
├── smartpick/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── core/                          ← app utama
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   ├── admin.py
│   └── management/
│       └── commands/
│           └── load_data.py       ← command untuk import CSV
├── engine/                        ← app AI engine
│   ├── tfidf_engine.py
│   ├── bm25_engine.py
│   ├── value_score.py
│   ├── intent_detector.py
│   └── recommender.py             ← orchestrator semua engine
└── templates/
    ├── base.html
    ├── index.html                 ← halaman utama + multi-step wizard
    └── result.html                ← halaman hasil rekomendasi
```

**requirements.txt harus berisi:**
```
django>=5.0
scikit-learn>=1.4
rank-bm25>=0.2.2
nltk>=3.8
pandas>=2.0
numpy>=1.26
python-dotenv>=1.0
whitenoise>=6.6
```

---

### TASK 2 — Database Model

Buat model `IphoneListing` di `core/models.py`:

```python
class IphoneListing(models.Model):
    # Data asli dari CSV
    platform = models.CharField(max_length=50)
    nama_toko = models.CharField(max_length=200)
    rating_produk = models.FloatField(default=0.0)
    has_rating = models.BooleanField(default=False)   # True jika rating > 0
    produk_terjual = models.IntegerField(default=0)
    kategori_seri = models.CharField(max_length=100)  # "iPhone 13 Series"
    kategori_varian = models.CharField(max_length=100) # "iPhone 13 Pro Max"
    penyimpanan = models.CharField(max_length=20)      # "128GB"
    battery_health = models.FloatField(null=True, blank=True)  # None jika N/A
    bh_imputed = models.BooleanField(default=False)    # True jika BH hasil imputasi
    harga = models.BigIntegerField()                   # dalam rupiah, integer
    wilayah_toko = models.CharField(max_length=100)
    link_pembelian = models.URLField(max_length=2000)
    
    # Kolom hasil engineering
    kondisi = models.CharField(max_length=50, default='unknown')
    # Nilai: 'like_new', 'mulus', 'normal', 'bekas', 'unknown'
    
    generasi = models.IntegerField()
    # Nilai: 11, 12, 13, 14, atau 15 (extract dari kategori_seri)
    
    is_pro = models.BooleanField(default=False)
    # True jika nama varian mengandung "Pro"
    
    penyimpanan_gb = models.IntegerField(default=128)
    # Nilai integer: 64, 128, 256, 512, 1024
    
    # Teks gabungan untuk BM25 indexing
    dokumen_teks = models.TextField()
    # Gabungan: "iphone 13 pro max 256gb mulus battery health 91 tokopedia surabaya"
    
    # Trust score (dihitung saat load data)
    trust_score = models.FloatField(default=0.0)  # 0.0 - 1.0
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-trust_score', '-battery_health']
    
    def __str__(self):
        return f"{self.kategori_varian} {self.penyimpanan} - {self.harga}"
```

---

### TASK 3 — Management Command untuk Load Data

Buat `core/management/commands/load_data.py` yang melakukan:

1. **Baca CSV** dengan pandas
2. **Preprocessing:**
   - Konversi harga: "Rp9.000.000" → 9000000
   - Normalisasi storage: "126GB"→"128GB", "1000GB"→"1TB"→1024, dst
   - Extract generasi: "iPhone 13 Series" → 13
   - Flag is_pro: True jika "Pro" ada di kategori_varian
   - Extract kondisi dari nama URL/varian menggunakan keyword:
     ```python
     kondisi_map = {
         'like_new': ['like new', 'likenew', 'like-new', 'baru'],
         'mulus':    ['mulus', 'fullset', 'lengkap', 'no minus'],
         'normal':   ['normal', 'second', 'bekas', 'eks'],
         'bekas':    ['minus', 'cacat', 'retak', 'pecah']
     }
     # Cek dari Link Pembelian URL dan Kategori Varian
     ```
   - Imputasi Battery Health:
     ```python
     # Hitung median BH per (kategori_varian, penyimpanan)
     # Listing tanpa BH → isi median, set bh_imputed=True
     # Jika group tidak punya data BH sama sekali → gunakan median global per seri
     ```
   - Hitung trust_score:
     ```python
     # Normalisasi min-max dari: rating_produk + log(produk_terjual+1)
     # has_rating bonus: listing dengan rating > 0 dapat +0.1
     ```
   - Buat dokumen_teks untuk BM25:
     ```python
     # f"{varian} {storage} {kondisi} battery health {bh} {platform} {wilayah}"
     # lowercase semua
     ```
3. **Simpan ke database** dengan bulk_create

---

### TASK 4 — AI Engine

#### `engine/intent_detector.py`
```python
"""
Deteksi intent user dari query awal menggunakan TF-IDF.
Mengembalikan: mode ('spec_first' atau 'budget_first') + sinyal per dimensi
"""

PRICE_TOKENS = ['murah', 'harga', 'budget', 'hemat', 'terjangkau', 'ekonomis', 'jutaan', 'ribu']
CAMERA_TOKENS = ['kamera', 'foto', 'portrait', 'video', 'fotografi', 'kualitas gambar', 'megapixel']
PERF_TOKENS = ['kencang', 'cepat', 'gaming', 'performa', 'ngelag', 'smooth', 'chipset', 'processor']
BATTERY_TOKENS = ['baterai', 'tahan lama', 'awet', 'battery', 'cas', 'charge', 'daya']
STORAGE_TOKENS = ['penyimpanan', 'storage', 'memori', 'gb', 'file', 'foto banyak', 'dokumen']

# Fungsi detect_intent(query: str) -> dict
# Return: {'mode': 'spec_first'|'budget_first', 'signals': {'camera': 0.8, 'battery': 0.2, ...}}
```

#### `engine/value_score.py`
```python
"""
Hitung ValueScore per listing berdasarkan bobot adaptif dari intent + dialog.

Formula:
ValueScore = (bh_norm * w_bh) + (gen_norm * w_gen) + (kondisi_norm * w_kondisi) + 
             (price_eff * w_price) + (trust * w_trust)

Bobot default (spec_first mode — tidak peduli harga):
  w_bh=0.35, w_gen=0.30, w_kondisi=0.20, w_price=0.00, w_trust=0.15

Bobot budget_first mode:
  w_bh=0.25, w_gen=0.15, w_kondisi=0.20, w_price=0.30, w_trust=0.10

Bobot bisa dimodifikasi berdasarkan jawaban dialog.
"""

KONDISI_SCORE = {'like_new': 1.0, 'mulus': 0.8, 'normal': 0.5, 'bekas': 0.2, 'unknown': 0.4}

# Fungsi: calculate(listing, weights: dict) -> float (0.0 - 1.0)
```

#### `engine/bm25_engine.py`
```python
"""
BM25 engine untuk re-ranking listing berdasarkan relevansi teks.
Menggunakan rank_bm25 library.

Alur:
1. Saat startup: index semua dokumen_teks dari database
2. Saat query: tokenize query → hitung BM25 score → return scores per listing

Tokenisasi:
- Lowercase
- Split spasi
- Hapus stopword Bahasa Indonesia sederhana: ['yang', 'dan', 'di', 'ke', 'dari', 'untuk', 'ini', 'itu']
- TIDAK perlu stemming untuk dataset ini (sudah keyword-based)
"""

# Class BM25Engine:
#   - __init__: load semua listing dari DB, build index
#   - score(query: str, listing_ids: list) -> dict {id: score}
```

#### `engine/recommender.py`
```python
"""
Orchestrator utama. Menerima input dari multi-step dialog, menggabungkan
TF-IDF intent detection + BM25 + ValueScore → return top 3 rekomendasi.

Alur:
1. detect_intent(query) → mode + signals
2. Terapkan hard filter dari dialog:
   - filter seri (jika user pilih seri tertentu)
   - filter storage minimum
   - filter BH minimum (hard cutoff, bukan soft)
   - filter kondisi minimum
3. BM25 scoring pada corpus yang sudah terfilter
4. ValueScore dengan bobot adaptif
5. Final score = 0.55 * bm25_normalized + 0.45 * value_score
6. Return top 3 dengan breakdown skor per dimensi + generate_reason()
"""

def get_recommendations(session_data: dict) -> list:
    """
    session_data berisi semua jawaban dialog:
    {
        'query': 'mau iphone kamera terbaik',
        'mode': 'spec_first',
        'seri': None,           # None = semua seri
        'storage_min': 128,
        'bh_min': 85,           # hard cutoff
        'kondisi_min': 'normal',
        'intent_signals': {'camera': 0.8, 'battery': 0.1, ...},
        'weights': {'bh': 0.35, 'gen': 0.30, ...}
    }
    """
    pass

def generate_reason(listing, weights: dict) -> str:
    """Generate kalimat penjelasan kenapa listing ini direkomendasikan."""
    pass
```

---

### TASK 5 — Views dan Multi-Step Wizard

Buat `core/views.py` dengan flow berikut:

```
GET  /              → index.html (form query awal)
POST /wizard/start  → simpan query ke session, redirect ke step 1
GET  /wizard/1      → step 1: tanya seri (atau skip)
POST /wizard/1      → simpan jawaban, redirect step 2
GET  /wizard/2      → step 2: tanya storage preference
POST /wizard/2      → simpan, redirect step 3
GET  /wizard/3      → step 3: tanya battery health minimum (slider)
POST /wizard/3      → simpan, redirect step 4
GET  /wizard/4      → step 4: tanya kondisi fisik minimum
POST /wizard/4      → simpan, redirect step 5
GET  /wizard/5      → step 5: konfirmasi + tampilkan preferensi
POST /wizard/5      → jalankan AI engine → redirect ke result
GET  /result        → tampilkan 3 rekomendasi + skor + link beli
GET  /restart       → clear session, redirect ke /
```

Gunakan Django session untuk menyimpan state wizard antar step.

---

### TASK 6 — Template UI

**Desain:** Minimalis, profesional, tidak neon. Warna utama: putih, abu-abu gelap, aksen biru tenang (#2563EB atau serupa). Font: Inter dari Google Fonts.

#### `templates/base.html`
- Navbar sederhana: logo "SmartPick" + tagline kecil
- Footer minimal
- Import Tailwind CSS via CDN

#### `templates/index.html`
- Hero section: judul besar "Temukan iPhone Bekas Terbaik Untukmu"
- Kotak input query besar, placeholder: "Contoh: mau iPhone yang kamera-nya bagus"
- Tombol mulai
- Bagian bawah: 3 ikon kecil menjelaskan cara kerja sistem (Tulis → Dialog → Rekomendasi)

#### `templates/wizard.html` (dipakai semua step)
- Progress bar di atas (Step X dari 5)
- Pertanyaan besar di tengah
- Pilihan jawaban sebagai card/tombol yang bisa diklik (bukan dropdown)
- Setiap step tampilkan "query kamu" di sidebar kecil sebagai konteks
- Tombol "Lanjut" dan "Kembali"

#### `templates/result.html`
- Tampilkan query asli + ringkasan preferensi user di atas
- 3 kartu produk side by side (atau stacked di mobile):
  - Badge rank (#1, #2, #3)
  - Nama varian + storage
  - Harga
  - Battery Health (dengan indikator warna: hijau ≥90, kuning 80-89, merah <80)
  - Kondisi fisik
  - Rating toko + produk terjual
  - Skor match (misal "94% cocok")
  - Kalimat alasan ("Direkomendasikan karena battery health tertinggi di kelasnya")
  - Tombol besar "Lihat di Tokopedia" → buka link_pembelian di tab baru
- Tombol "Cari lagi" di bawah

---

### TASK 7 — Halaman Admin Sederhana

Aktifkan Django Admin dan daftarkan model `IphoneListing` dengan filter:
- Filter by: Kategori Seri, Penyimpanan, Kondisi, Platform
- Search by: Nama Toko, Kategori Varian
- List display: varian, storage, harga, BH, kondisi, trust_score, platform

---

## INSTRUKSI PENTING UNTUK CLAUDE CODE

1. **Kerjakan berurutan** Task 1 → 2 → 3 → 4 → 5 → 6 → 7. Jangan loncat.

2. **Setelah selesai tiap task**, jalankan dan verifikasi tidak ada error sebelum lanjut ke task berikutnya.

3. **Setelah Task 3**, jalankan:
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   python manage.py load_data --file data/data_iphone_v2.csv
   ```
   Pastikan 723 listing berhasil diimport tanpa error.

4. **Setelah Task 4**, buat file `engine/test_engine.py` dan test:
   ```python
   # Test 1: query spec-first
   result = get_recommendations({'query': 'mau yang terbaik tidak peduli harga', ...})
   assert len(result) == 3
   assert result[0]['final_score'] > result[1]['final_score']
   
   # Test 2: query budget-first
   result = get_recommendations({'query': 'mau yang murah tapi bagus', ...})
   # Pastikan weight price > 0
   ```

5. **Jangan gunakan JavaScript framework** (React, Vue, dll). Cukup Tailwind + vanilla JS minimal untuk interaksi wizard.

6. **Semua teks UI dalam Bahasa Indonesia.**

7. **Simpan dataset** di folder `data/data_iphone_v2.csv` relatif dari root proyek.

8. **Jika ada kolom Battery Health bernilai "N/A"** (string), treat sebagai null/None, bukan float.

9. **Untuk BM25**, index dibangun sekali saat server start (di `AppConfig.ready()` atau lazy-load pertama kali). Jangan rebuild index per request.

10. **Final check sebelum selesai:**
    ```bash
    python manage.py runserver
    ```
    Buka http://127.0.0.1:8000 dan pastikan:
    - Halaman index tampil
    - Wizard bisa jalan 5 step
    - Halaman result menampilkan 3 rekomendasi dengan link yang bisa diklik

---

## OUTPUT YANG DIHARAPKAN

Ketika selesai, sistem harus bisa:
- User tulis "mau iPhone kamera terbaik tidak peduli harga" → sistem deteksi intent spec-first → dialog 5 step → tampil 3 rekomendasi iPhone Pro series dengan BH tertinggi + link langsung ke Tokopedia
- User tulis "mau iPhone murah budget 5 juta" → sistem deteksi intent budget-first → bobot harga naik → rekomendasi iPhone 11/12 series yang value-for-money
- Dua user dengan query sama tapi jawaban dialog berbeda → dapat rekomendasi berbeda

Mulai dari Task 1 sekarang.
