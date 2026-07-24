"""
Fuzzy Inference System (Mamdani) untuk menilai "kualitas nilai" (value quality)
sebuah listing dari tiga variabel yang secara alami bersifat samar/relatif:
battery health, efisiensi harga, dan trust score toko.

Alasan pemakaian fuzzy logic (bukan sekadar bobot linear): ketiga variabel ini
tidak punya batas tegas antara "bagus" dan "kurang bagus" -- battery health 84%
dan 86% praktis setara secara persepsi pengguna, padahal skor linear akan
membedakannya secara proporsional. Fuzzy logic memodelkan pergeseran bertahap
ini lewat fungsi keanggotaan dan menggabungkan tiga variabel lewat basis
aturan IF-THEN, bukan penjumlahan berbobot semata.

Alur: fuzzifikasi (nilai crisp -> derajat keanggotaan tiap himpunan fuzzy)
-> evaluasi aturan (operator MIN untuk AND, agregasi MAX antar aturan dengan
label output sama) -> defuzzifikasi (metode centroid) -> skor crisp 0..1.
"""


def _trapezoid(x, a, b, c, d):
    # Urutan pengecekan plateau (b<=x<=c) LEBIH DULU dari batas luar penting:
    # ketika c == d (plateau rata hingga ujung kanan domain, mis. BH "tinggi"
    # yang mentok di 100), memeriksa x >= d lebih dulu akan salah menganggap
    # x == c == d berada di luar himpunan, padahal seharusnya keanggotaan
    # penuh (1.0).
    if a < x < b:
        return (x - a) / (b - a)
    if b <= x <= c:
        return 1.0
    if c < x < d:
        return (d - x) / (d - c)
    return 0.0


def _triangle(x, a, b, c):
    if x <= a or x >= c:
        return 0.0
    if x == b:
        return 1.0
    if x < b:
        return (x - a) / (b - a)
    return (c - x) / (c - b)


# --- Himpunan fuzzy input ---------------------------------------------------

BH_SETS = {
    'rendah': lambda x: _trapezoid(x, 0, 0, 60, 75),
    'sedang': lambda x: _triangle(x, 65, 80, 95),
    'tinggi': lambda x: _trapezoid(x, 85, 95, 100, 100),
}

# PriceEff dan Trust sama-sama berskala 0..1 sehingga memakai bentuk yang sama.
UNIT_SETS = {
    'rendah': lambda x: _trapezoid(x, 0, 0, 0.3, 0.5),
    'sedang': lambda x: _triangle(x, 0.3, 0.5, 0.7),
    'tinggi': lambda x: _trapezoid(x, 0.5, 0.7, 1, 1),
}

# --- Himpunan fuzzy output (ValueQuality, 0..1) -----------------------------

VALUE_SETS = {
    'rendah': lambda x: _trapezoid(x, 0, 0, 0.25, 0.45),
    'sedang': lambda x: _triangle(x, 0.3, 0.5, 0.7),
    'tinggi': lambda x: _trapezoid(x, 0.55, 0.75, 1, 1),
}

# --- Basis aturan (Mamdani) --------------------------------------------------
# Setiap aturan: (kondisi antesenden sebagai dict variabel->label, label output).
# Variabel yang tidak disebut dalam sebuah aturan tidak ikut dalam operator MIN
# (diperlakukan sebagai "don't care" untuk aturan tersebut).
#
# Setiap aturan WAJIB menyertakan variabel `bh` di antesedennya. Rancangan
# awal sempat memuat aturan yang hanya bergantung pada price+trust (tanpa bh)
# -- pengujian menemukan bahwa dengan agregasi MAX, satu aturan semacam itu
# bisa saja menjenuhkan bucket output "tinggi" sendirian, sehingga battery
# health berhenti membedakan skor akhir ketika harga dan trust sama-sama
# tinggi. Aturan berikut memastikan bh selalu ikut menentukan konsekuen,
# sehingga trust/price berperan sebagai modifier, bukan pengganti bh.
RULES = [
    ({'bh': 'tinggi', 'trust': 'tinggi'}, 'tinggi'),
    ({'bh': 'tinggi', 'price': 'tinggi'}, 'tinggi'),
    ({'bh': 'tinggi', 'trust': 'sedang', 'price': 'sedang'}, 'tinggi'),
    ({'bh': 'tinggi', 'trust': 'rendah', 'price': 'rendah'}, 'sedang'),
    ({'bh': 'sedang', 'trust': 'tinggi', 'price': 'tinggi'}, 'tinggi'),
    ({'bh': 'sedang', 'trust': 'rendah', 'price': 'rendah'}, 'rendah'),
    ({'bh': 'sedang'}, 'sedang'),
    ({'bh': 'rendah', 'trust': 'tinggi', 'price': 'tinggi'}, 'sedang'),
    ({'bh': 'rendah'}, 'rendah'),
]

_UNIVERSE = [i / 100 for i in range(101)]


def fuzzify(bh: float, price_eff: float, trust: float) -> dict:
    return {
        'bh': {label: fn(bh) for label, fn in BH_SETS.items()},
        'price': {label: fn(price_eff) for label, fn in UNIT_SETS.items()},
        'trust': {label: fn(trust) for label, fn in UNIT_SETS.items()},
    }


def infer_quality(bh: float, price_eff: float, trust: float) -> float:
    """Jalankan FIS Mamdani penuh: fuzzifikasi -> evaluasi aturan -> defuzzifikasi centroid."""
    degrees = fuzzify(bh, price_eff, trust)

    aggregated = {'rendah': 0.0, 'sedang': 0.0, 'tinggi': 0.0}
    for antecedent, output_label in RULES:
        strength = min(degrees[var][label] for var, label in antecedent.items())
        aggregated[output_label] = max(aggregated[output_label], strength)

    numerator = 0.0
    denominator = 0.0
    for x in _UNIVERSE:
        mu = max(min(aggregated[label], fn(x)) for label, fn in VALUE_SETS.items())
        numerator += mu * x
        denominator += mu

    return round(numerator / denominator, 4) if denominator > 0 else 0.5
