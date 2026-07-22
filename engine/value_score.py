"""
Hitung ValueScore per listing berdasarkan bobot adaptif dari intent + dialog.

Formula:
ValueScore = (bh_norm * w_bh) + (gen_norm * w_gen) + (kondisi_norm * w_kondisi) +
             (price_eff * w_price) + (trust * w_trust)

Bobot default (spec_first mode — tidak peduli harga):
  w_bh=0.35, w_gen=0.30, w_kondisi=0.20, w_price=0.00, w_trust=0.15

Bobot budget_first mode:
  w_bh=0.25, w_gen=0.15, w_kondisi=0.20, w_price=0.30, w_trust=0.10
"""

from functools import lru_cache

from django.db.models import Max, Min

KONDISI_SCORE = {'like_new': 1.0, 'mulus': 0.8, 'normal': 0.5, 'bekas': 0.2, 'unknown': 0.4}

SPEC_FIRST_WEIGHTS = {'bh': 0.35, 'gen': 0.30, 'kondisi': 0.20, 'price': 0.00, 'trust': 0.15}
BUDGET_FIRST_WEIGHTS = {'bh': 0.25, 'gen': 0.15, 'kondisi': 0.20, 'price': 0.30, 'trust': 0.10}

GENERASI_MIN, GENERASI_MAX = 11, 15


@lru_cache(maxsize=1)
def _harga_bounds():
    from core.models import IphoneListing

    agg = IphoneListing.objects.aggregate(min_harga=Min('harga'), max_harga=Max('harga'))
    return agg['min_harga'] or 0, agg['max_harga'] or 1


def clear_harga_bounds_cache():
    _harga_bounds.cache_clear()


def _normalize(value, lo, hi):
    if hi == lo:
        return 0.5
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def calculate(listing, weights: dict) -> float:
    bh = listing.battery_health if listing.battery_health is not None else 0.0
    bh_norm = max(0.0, min(1.0, bh / 100))

    gen_norm = _normalize(listing.generasi, GENERASI_MIN, GENERASI_MAX)
    kondisi_norm = KONDISI_SCORE.get(listing.kondisi, 0.4)

    lo, hi = _harga_bounds()
    price_norm = _normalize(listing.harga, lo, hi)
    price_eff = 1.0 - price_norm  # semakin murah, semakin tinggi skor

    trust = max(0.0, min(1.0, listing.trust_score))

    score = (
        bh_norm * weights.get('bh', 0.0)
        + gen_norm * weights.get('gen', 0.0)
        + kondisi_norm * weights.get('kondisi', 0.0)
        + price_eff * weights.get('price', 0.0)
        + trust * weights.get('trust', 0.0)
    )
    return round(max(0.0, min(1.0, score)), 4)
