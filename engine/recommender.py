"""
Orchestrator utama. Menerima input dari wizard multi-step, menggabungkan
TF-IDF intent detection + BM25 + ValueScore -> return top 3 rekomendasi.

Alur:
1. detect_intent(query) -> mode + signals (query kosong jika wizard tidak
   mengumpulkan teks bebas -- BM25/TF-IDF tetap berjalan, hanya tidak
   berkontribusi pada skor karena tidak ada token untuk dicocokkan)
2. Terapkan hard filter dari wizard:
   - filter seri, varian model, range harga
   - filter storage minimum
   - filter BH minimum (hard cutoff, bukan soft)
   - filter kondisi minimum
   - filter status garansi
   Jika hasil filter kosong, relaksasi kondisi & garansi lalu filter ulang.
3. BM25 scoring pada corpus yang sudah terfilter
4. ValueScore dengan bobot adaptif (calculate_adaptive_weights)
5. Final score = 0.55 * bm25_normalized + 0.45 * value_score;
   bobot dipindah seluruhnya ke ValueScore (1.0) saat BM25 tidak aktif
   (query kosong / tidak ada token yang cocok), lihat _score_and_rank
6. Return top 3 dengan breakdown skor per dimensi + generate_reason()
"""

from core.models import IphoneListing

from .bm25_engine import BM25Engine
from .intent_detector import detect_intent, extract_price_ceiling
from .value_score import calculate as calculate_value_score

KONDISI_ORDER = ['bekas', 'unknown', 'normal', 'mulus', 'like_new']

BH_LABEL = {
    'tinggi': 90,
    'baik': 80,
}

BASE_WEIGHTS = {'bh': 0.30, 'gen': 0.25, 'kondisi': 0.20, 'price': 0.15, 'trust': 0.10}

# Bobot yang diberikan ke dimensi yang dipilih user sebagai "Prioritas Utama"
# (wizard step 8); sisanya (1 - PRIORITY_BOOST) dibagi proporsional ke empat
# dimensi lain sesuai rasio BASE_WEIGHTS. Dipilih eksplisit oleh user, sehingga
# menggantikan (bukan menambah) penyesuaian otomatis di bawah -- user yang
# sudah menyatakan prioritasnya tidak perlu ditebak lagi lewat heuristik.
PRIORITY_BOOST = 0.50


def _boost_priority(priority: str) -> dict:
    others = {k: v for k, v in BASE_WEIGHTS.items() if k != priority}
    others_total = sum(others.values())
    remaining = 1 - PRIORITY_BOOST
    weights = {k: (v / others_total) * remaining for k, v in others.items()}
    weights[priority] = PRIORITY_BOOST
    return weights


def calculate_adaptive_weights(session_data: dict) -> dict:
    """Hitung bobot ValueScore berdasarkan jawaban wizard (prioritas, varian, garansi, budget)."""
    priority = session_data.get('priority')
    if priority in BASE_WEIGHTS:
        weights = _boost_priority(priority)
        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}

    weights = dict(BASE_WEIGHTS)

    if session_data.get('price_weight_zero'):
        weights['bh'] += 0.08
        weights['gen'] += 0.07
        weights['price'] = 0.0

    if session_data.get('varian') in ('pro', 'pro_max'):
        weights['gen'] += 0.05
        weights['trust'] -= 0.05

    if session_data.get('garansi') == 'resmi':
        weights['trust'] += 0.10
        weights['kondisi'] -= 0.10

    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


def _apply_hard_filters(queryset, session_data: dict):
    seri = session_data.get('seri')
    if seri:
        queryset = queryset.filter(kategori_seri=seri)

    varian = session_data.get('varian')
    if varian:
        queryset = queryset.filter(varian_model=varian)

    storage_min = session_data.get('storage_min')
    if storage_min:
        queryset = queryset.filter(penyimpanan_gb__gte=storage_min)

    bh_min = session_data.get('bh_min')
    if bh_min:
        queryset = queryset.filter(battery_health__gte=bh_min)

    kondisi_min = session_data.get('kondisi_min')
    if kondisi_min in KONDISI_ORDER:
        allowed = KONDISI_ORDER[KONDISI_ORDER.index(kondisi_min):]
        queryset = queryset.filter(kondisi__in=allowed)

    garansi = session_data.get('garansi')
    if garansi:
        queryset = queryset.filter(garansi=garansi)

    harga_min = session_data.get('harga_min')
    if harga_min:
        queryset = queryset.filter(harga__gte=harga_min)

    harga_max = session_data.get('harga_max') or extract_price_ceiling(session_data.get('query', ''))
    if harga_max:
        queryset = queryset.filter(harga__lte=harga_max)

    return queryset


def _filtered_listings(session_data: dict):
    """Return (listings, relaxed). Jika filter penuh menghasilkan corpus kosong,
    relaksasi kondisi & garansi lalu coba lagi."""
    listings = list(_apply_hard_filters(IphoneListing.objects.all(), session_data))
    if listings:
        return listings, False

    relaxed_data = dict(session_data)
    relaxed_data['kondisi_min'] = None
    relaxed_data['garansi'] = None
    listings = list(_apply_hard_filters(IphoneListing.objects.all(), relaxed_data))
    return listings, True


BM25_WEIGHT = 0.55
VALUE_WEIGHT = 0.45


def _score_and_rank(listings, session_data: dict) -> list:
    query = session_data.get('query', '')
    weights = session_data.get('weights') or calculate_adaptive_weights(session_data)

    bm25 = BM25Engine.get_instance()
    listing_ids = [listing.id for listing in listings]
    bm25_scores = bm25.score(query, listing_ids)
    max_bm25 = max(bm25_scores.values()) if bm25_scores else 0.0

    # Wizard saat ini tidak menjaring kueri bebas, sehingga
    # BM25 selalu bernilai nol untuk seluruh kandidat. Menghitung tetap dengan
    # bobot 0,55/0,45 pada kondisi itu akan memotong final_score maksimal ke
    # 0,45 -- match% jadi terkompresi ke rentang sempit dan seolah statis,
    # padahal ValueScore (termasuk komponen fuzzy dan Prioritas Utama) sudah
    # membedakan kandidat dengan baik. Saat BM25 tidak aktif, bobotnya
    # dipindahkan seluruhnya ke ValueScore; begitu kolom kueri bebas tersedia
    # dan BM25 kembali bernilai non-nol, split 0,55/0,45 pada Persamaan 6
    # otomatis berlaku lagi.
    bm25_active = max_bm25 > 0
    bm25_weight = BM25_WEIGHT if bm25_active else 0.0
    value_weight = VALUE_WEIGHT if bm25_active else 1.0

    results = []
    for listing in listings:
        bm25_raw = bm25_scores.get(listing.id, 0.0)
        bm25_norm = (bm25_raw / max_bm25) if max_bm25 > 0 else 0.0
        value_score = calculate_value_score(listing, weights)
        final_score = bm25_weight * bm25_norm + value_weight * value_score

        results.append({
            'listing': listing,
            'bm25_score': round(bm25_norm, 4),
            'value_score': round(value_score, 4),
            'final_score': round(final_score, 4),
            'match_percent': round(final_score * 100),
            'reason': generate_reason(listing, weights),
        })

    results.sort(key=lambda r: r['final_score'], reverse=True)
    return results[:3]


def get_recommendations_detailed(session_data: dict) -> dict:
    """
    session_data berisi jawaban wizard, mis.:
    {
        'seri': 'iPhone 13 Series',      # atau None
        'varian': 'pro_max',             # atau None
        'harga_min': 9000000,
        'harga_max': 13000000,
        'price_weight_zero': False,
        'storage_min': 256,              # atau None
        'bh_min': 85,                    # atau None
        'kondisi_min': 'mulus',          # atau None
        'garansi': 'tidak_ada',          # atau None
    }
    Return {'results': [...top 3...], 'relaxed': bool}
    """
    detect_intent(session_data.get('query', ''))  # sinyal intent (kompatibilitas alur lama)

    listings, relaxed = _filtered_listings(session_data)
    if not listings:
        return {'results': [], 'relaxed': relaxed}

    return {'results': _score_and_rank(listings, session_data), 'relaxed': relaxed}


def get_recommendations(session_data: dict) -> list:
    """Kompatibel dengan pemanggil lama: hanya mengembalikan daftar top 3."""
    return get_recommendations_detailed(session_data)['results']


def generate_reason(listing, weights: dict) -> str:
    """Generate kalimat penjelasan kenapa listing ini direkomendasikan."""
    if not weights or max(weights.values()) <= 0:
        dominant = 'bh'
    else:
        dominant = max(weights, key=weights.get)

    harga_str = f'Rp{listing.harga:,}'.replace(',', '.')

    if dominant == 'bh':
        bh = round(listing.battery_health or 0)
        label = 'sangat tinggi' if bh >= BH_LABEL['tinggi'] else 'baik' if bh >= BH_LABEL['baik'] else 'cukup'
        return f'Battery health {bh}% tergolong {label} di kelasnya.'

    if dominant == 'gen':
        return f'{listing.kategori_varian} adalah salah satu generasi terbaru pada hasil pencarianmu.'

    if dominant == 'kondisi':
        kondisi_label = listing.kondisi.replace('_', ' ')
        return f'Kondisi fisik "{kondisi_label}" sesuai dengan preferensimu.'

    if dominant == 'price':
        return f'Harga {harga_str} tergolong value-for-money untuk spesifikasi yang didapat.'

    if dominant == 'trust':
        return (
            f'Toko {listing.nama_toko} terpercaya dengan {listing.produk_terjual} produk terjual '
            f'dan rating {listing.rating_produk:.1f}.'
        )

    return 'Direkomendasikan berdasarkan kombinasi skor terbaik.'
