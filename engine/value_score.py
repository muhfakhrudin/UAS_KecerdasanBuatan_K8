"""
Hitung ValueScore per listing berdasarkan bobot adaptif dari intent + dialog.

Formula:
ValueScore = (FuzzyQuality(bh, price_eff, trust) * w_fuzzy) +
             (kondisi_norm * w_kondisi) + (gen_norm * w_gen)
dengan w_fuzzy = w_bh + w_price + w_trust.

FuzzyQuality dihitung oleh fuzzy_engine.infer_quality (Mamdani FIS) karena
battery health, efisiensi harga, dan trust toko adalah tiga variabel yang
batasnya samar (mis. BH 84% vs 86% praktis setara secara persepsi pembeli),
sehingga digabungkan lewat basis aturan fuzzy, bukan penjumlahan linear.
Kondisi fisik dan generasi tetap berupa atribut kategorikal/ordinal yang
batasnya tegas, sehingga tetap dihitung sebagai suku berbobot biasa.

Bobot default (spec_first mode — tidak peduli harga):
  w_bh=0.35, w_gen=0.30, w_kondisi=0.20, w_price=0.00, w_trust=0.15

Bobot budget_first mode:
  w_bh=0.25, w_gen=0.15, w_kondisi=0.20, w_price=0.30, w_trust=0.10
"""

from functools import lru_cache

from .fuzzy_engine import infer_quality

KONDISI_SCORE = {'like_new': 1.0, 'mulus': 0.8, 'normal': 0.5, 'bekas': 0.2, 'unknown': 0.4}

SPEC_FIRST_WEIGHTS = {'bh': 0.35, 'gen': 0.30, 'kondisi': 0.20, 'price': 0.00, 'trust': 0.15}
BUDGET_FIRST_WEIGHTS = {'bh': 0.25, 'gen': 0.15, 'kondisi': 0.20, 'price': 0.30, 'trust': 0.10}

GENERASI_MIN, GENERASI_MAX = 11, 15


@lru_cache(maxsize=1)
def _harga_bounds():
    """
    Batas normalisasi harga pakai persentil (P5-P95), bukan min/max mentah.
    Dataset ini punya outlier ekstrem (mis. Rp410rb dan Rp55jt) yang membuat
    min-max normalization "menenggelamkan" perbedaan harga antar listing normal
    -- akibatnya ValueScore nyaris tidak membedakan listing Rp1jt vs Rp9jt.
    Percentile clipping membuat sinyal harga jauh lebih diskriminatif untuk
    mayoritas listing, dengan listing ekstrem tetap ter-clamp ke 0.0/1.0.
    """
    from core.models import IphoneListing

    values = sorted(IphoneListing.objects.values_list('harga', flat=True))
    n = len(values)
    if n == 0:
        return 0, 1
    if n < 20:
        return values[0], values[-1]

    lo = values[int(n * 0.05)]
    hi = values[int(n * 0.95)]
    if hi == lo:
        return values[0], values[-1]
    return lo, hi


def clear_harga_bounds_cache():
    _harga_bounds.cache_clear()


def _normalize(value, lo, hi):
    if hi == lo:
        return 0.5
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def calculate(listing, weights: dict) -> float:
    bh = listing.battery_health if listing.battery_health is not None else 0.0

    gen_norm = _normalize(listing.generasi, GENERASI_MIN, GENERASI_MAX)
    kondisi_norm = KONDISI_SCORE.get(listing.kondisi, 0.4)

    lo, hi = _harga_bounds()
    price_norm = _normalize(listing.harga, lo, hi)
    price_eff = 1.0 - price_norm  # semakin murah, semakin tinggi skor

    trust = max(0.0, min(1.0, listing.trust_score))

    fuzzy_quality = infer_quality(bh, price_eff, trust)
    w_fuzzy = weights.get('bh', 0.0) + weights.get('price', 0.0) + weights.get('trust', 0.0)

    score = (
        fuzzy_quality * w_fuzzy
        + kondisi_norm * weights.get('kondisi', 0.0)
        + gen_norm * weights.get('gen', 0.0)
    )
    return round(max(0.0, min(1.0, score)), 4)
