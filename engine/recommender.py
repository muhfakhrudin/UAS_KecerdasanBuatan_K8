"""
Orchestrator utama. Menerima input dari multi-step dialog, menggabungkan
TF-IDF intent detection + BM25 + ValueScore -> return top 3 rekomendasi.

Alur:
1. detect_intent(query) -> mode + signals
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

from core.models import IphoneListing

from .bm25_engine import BM25Engine
from .intent_detector import detect_intent
from .value_score import BUDGET_FIRST_WEIGHTS, SPEC_FIRST_WEIGHTS
from .value_score import calculate as calculate_value_score

KONDISI_ORDER = ['bekas', 'unknown', 'normal', 'mulus', 'like_new']

BH_LABEL = {
    'tinggi': 90,
    'baik': 80,
}


def _apply_hard_filters(queryset, session_data: dict):
    seri = session_data.get('seri')
    if seri:
        queryset = queryset.filter(kategori_seri=seri)

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

    return queryset


def get_recommendations(session_data: dict) -> list:
    """
    session_data berisi semua jawaban dialog:
    {
        'query': 'mau iphone kamera terbaik',
        'mode': 'spec_first',
        'seri': None,
        'storage_min': 128,
        'bh_min': 85,
        'kondisi_min': 'normal',
        'intent_signals': {...},
        'weights': {'bh': 0.35, 'gen': 0.30, ...},
    }
    """
    query = session_data.get('query', '')
    intent = detect_intent(query)

    mode = session_data.get('mode') or intent['mode']
    weights = session_data.get('weights') or (
        BUDGET_FIRST_WEIGHTS if mode == 'budget_first' else SPEC_FIRST_WEIGHTS
    )

    queryset = _apply_hard_filters(IphoneListing.objects.all(), session_data)
    listings = list(queryset)

    if not listings:
        return []

    bm25 = BM25Engine.get_instance()
    listing_ids = [listing.id for listing in listings]
    bm25_scores = bm25.score(query, listing_ids)
    max_bm25 = max(bm25_scores.values()) if bm25_scores else 0.0

    results = []
    for listing in listings:
        bm25_raw = bm25_scores.get(listing.id, 0.0)
        bm25_norm = (bm25_raw / max_bm25) if max_bm25 > 0 else 0.0
        value_score = calculate_value_score(listing, weights)
        final_score = 0.55 * bm25_norm + 0.45 * value_score

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
