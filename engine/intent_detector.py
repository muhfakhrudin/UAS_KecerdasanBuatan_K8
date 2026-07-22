"""
Deteksi intent user dari query awal menggunakan TF-IDF.
Mengembalikan: mode ('spec_first' atau 'budget_first') + sinyal per dimensi
"""

import re

from .tfidf_engine import compute_similarity

PRICE_CEILING_PATTERN = re.compile(
    r'(?:di\s*bawah|dibawah|kurang\s*dari|maksimal|maks\b|max\b|budget|sekitar)'
    r'\s*(?:rp\.?\s*)?(\d+(?:[.,]\d+)?)\s*(jut\w*|jt\b|rib\w*|rb\b)?'
)

PRICE_TOKENS = ['murah', 'harga', 'budget', 'hemat', 'terjangkau', 'ekonomis', 'jutaan', 'ribu']
CAMERA_TOKENS = ['kamera', 'foto', 'portrait', 'video', 'fotografi', 'kualitas gambar', 'megapixel']
PERF_TOKENS = ['kencang', 'cepat', 'gaming', 'performa', 'ngelag', 'smooth', 'chipset', 'processor']
BATTERY_TOKENS = ['baterai', 'tahan lama', 'awet', 'battery', 'cas', 'charge', 'daya']
STORAGE_TOKENS = ['penyimpanan', 'storage', 'memori', 'gb', 'file', 'foto banyak', 'dokumen']

DIMENSIONS = {
    'price': PRICE_TOKENS,
    'camera': CAMERA_TOKENS,
    'performance': PERF_TOKENS,
    'battery': BATTERY_TOKENS,
    'storage': STORAGE_TOKENS,
}


def detect_intent(query: str) -> dict:
    """Return {'mode': 'spec_first'|'budget_first', 'signals': {'camera': 0.8, ...}}"""
    query_clean = (query or '').lower().strip()

    dimension_names = list(DIMENSIONS.keys())
    documents = [' '.join(tokens) for tokens in DIMENSIONS.values()]
    similarities = compute_similarity(query_clean, documents)

    raw_signals = dict(zip(dimension_names, similarities))
    max_signal = max(raw_signals.values()) if raw_signals else 0.0

    if max_signal > 0:
        signals = {name: round(score / max_signal, 4) for name, score in raw_signals.items()}
    else:
        signals = {name: 0.0 for name in raw_signals}

    price_signal = signals.get('price', 0.0)
    is_price_dominant = price_signal > 0 and price_signal == max(signals.values())
    mode = 'budget_first' if is_price_dominant else 'spec_first'

    return {'mode': mode, 'signals': signals}


def extract_price_ceiling(query: str):
    """
    Ekstrak batas harga maksimum dari teks bebas, mis. "dibawah 4 jutaan",
    "maksimal 4jt", "budget 500 ribu". Return int rupiah, atau None jika
    tidak ada pola harga yang terdeteksi.
    """
    query_clean = (query or '').lower()
    match = PRICE_CEILING_PATTERN.search(query_clean)
    if not match:
        return None

    number = float(match.group(1).replace(',', '.'))
    unit = match.group(2) or ''

    if unit.startswith('jut') or unit == 'jt':
        return int(number * 1_000_000)
    if unit.startswith('rib') or unit == 'rb':
        return int(number * 1_000)
    # Tanpa satuan eksplisit: angka kecil diasumsikan "juta" (kebiasaan user
    # marketplace, mis. "dibawah 4" -> 4 juta), angka besar dianggap rupiah utuh.
    if number < 1000:
        return int(number * 1_000_000)
    return int(number)
