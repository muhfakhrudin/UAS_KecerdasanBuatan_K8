"""
Tampilkan breakdown lengkap mekanisme AI (TF-IDF intent detection + BM25 +
ValueScore + FinalScore) untuk satu set jawaban wizard tertentu -- dipakai
untuk mereplikasi input yang sama seperti yang dicoba lewat antarmuka wizard
(mis. dari tangkapan layar halaman hasil) dan melihat kontribusi tiap
algoritma secara eksplisit, bukan cuma hasil akhirnya.

Jalankan:
    python manage.py algorithm_breakdown --seri "iPhone 12 Series" --varian reguler \
        --harga-max 4000000 --storage-min 128 --bh-min 90 --kondisi-min normal \
        --garansi resmi --priority trust

    # dengan kueri bebas untuk menguji TF-IDF/BM25 sekaligus:
    python manage.py algorithm_breakdown --query "iphone 12 mulus battery health tinggi"
"""
from django.core.management.base import BaseCommand

from engine.bm25_engine import BM25Engine
from engine.intent_detector import detect_intent
from engine.recommender import _filtered_listings, calculate_adaptive_weights
from engine.value_score import calculate as calculate_value_score


class Command(BaseCommand):
    help = (
        'Tampilkan breakdown TF-IDF (intent) + BM25 + ValueScore + FinalScore '
        'untuk satu skenario wizard tertentu -- untuk verifikasi/demo langsung.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--seri', default=None, help='mis. "iPhone 12 Series"')
        parser.add_argument('--varian', default=None, help='reguler|mini|plus|pro|pro_max')
        parser.add_argument('--harga-min', type=int, default=0)
        parser.add_argument('--harga-max', type=int, default=999_999_999)
        parser.add_argument('--price-weight-zero', action='store_true')
        parser.add_argument('--storage-min', type=int, default=None)
        parser.add_argument('--bh-min', type=int, default=None)
        parser.add_argument('--kondisi-min', default=None, help='bekas|normal|mulus|like_new')
        parser.add_argument('--garansi', default=None, help='resmi|inter|beacukai|tidak_ada')
        parser.add_argument('--priority', default=None, help='bh|gen|kondisi|price|trust')
        parser.add_argument(
            '--query', default='',
            help='Kueri bebas untuk BM25/TF-IDF (default kosong, seperti wizard produksi saat ini).',
        )
        parser.add_argument('--top', type=int, default=5, help='Jumlah kandidat ditampilkan (default 5).')

    def handle(self, *args, **options):
        session_data = {
            'seri': options['seri'],
            'varian': options['varian'],
            'harga_min': options['harga_min'],
            'harga_max': options['harga_max'],
            'price_weight_zero': options['price_weight_zero'],
            'storage_min': options['storage_min'],
            'bh_min': options['bh_min'],
            'kondisi_min': options['kondisi_min'],
            'garansi': options['garansi'],
            'priority': options['priority'],
            'query': options['query'],
        }

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('=== Input (setara jawaban wizard) ==='))
        for key in ['seri', 'varian', 'harga_min', 'harga_max', 'storage_min',
                    'bh_min', 'kondisi_min', 'garansi', 'priority', 'query']:
            self.stdout.write(f'  {key:14s}: {session_data[key]!r}')

        listings, relaxed = _filtered_listings(session_data)
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('=== 1. Hard Filter ==='))
        self.stdout.write(f'Kandidat lolos: {len(listings)}' + (' (filter kondisi/garansi DIRELAKSASI karena hasil awal kosong)' if relaxed else ''))
        if not listings:
            self.stdout.write(self.style.ERROR('Tidak ada kandidat sama sekali, bahkan setelah relaksasi.'))
            return

        weights = calculate_adaptive_weights(session_data)
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('=== 2. Bobot Adaptif ValueScore (Persamaan 7) ==='))
        self.stdout.write('  ' + ', '.join(f'{k}={round(v,3)}' for k, v in weights.items()))

        intent = detect_intent(session_data['query'])
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('=== 3. TF-IDF Intent Detection (modul intent_detector) ==='))
        self.stdout.write(f"  mode  : {intent['mode']}")
        self.stdout.write('  signals: ' + ', '.join(f'{k}={v}' for k, v in intent['signals'].items()))
        if not session_data['query']:
            self.stdout.write(self.style.WARNING(
                '  (query kosong -> seluruh signal 0, TF-IDF tidak berkontribusi -- '
                'ini kondisi wizard produksi saat ini)'
            ))

        bm25 = BM25Engine.get_instance()
        ids = [l.id for l in listings]
        bm25_raw = bm25.score(session_data['query'], ids)
        max_bm25 = max(bm25_raw.values()) if bm25_raw else 0.0
        bm25_active = max_bm25 > 0
        bm25_weight = 0.55 if bm25_active else 0.0
        value_weight = 0.45 if bm25_active else 1.0

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('=== 4. BM25 (Persamaan 4-5) ==='))
        self.stdout.write(f'  BM25 aktif: {bm25_active} (max_bm25={round(max_bm25,4)})')
        self.stdout.write(f'  Bobot dipakai di Persamaan 6: BM25={bm25_weight} | ValueScore={value_weight}'
                           + ('' if bm25_active else '  (fallback: BM25 kosong, seluruh bobot ke ValueScore)'))

        rows = []
        for l in listings:
            b_raw = bm25_raw.get(l.id, 0.0)
            b_norm = (b_raw / max_bm25) if max_bm25 > 0 else 0.0
            value = calculate_value_score(l, weights)
            final = bm25_weight * b_norm + value_weight * value
            rows.append((l, b_norm, value, final))

        rows.sort(key=lambda r: r[3], reverse=True)

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(f'=== 5. Hasil (Persamaan 6), top {options["top"]} dari {len(rows)} ==='))
        header = f"{'#':>2} | {'Listing':38s} | {'Harga':>12} | {'BH':>4} | {'Kondisi':>8} | {'Trust':>5} | {'BM25':>6} | {'Value':>6} | {'Final':>6} | Match"
        self.stdout.write(header)
        self.stdout.write('-' * len(header))
        for i, (l, b_norm, value, final) in enumerate(rows[:options['top']], start=1):
            label = f'{l.kategori_varian} {l.penyimpanan}'[:38]
            self.stdout.write(
                f"{i:>2} | {label:38s} | Rp{l.harga:>10,} | {l.battery_health:>3.0f}% | "
                f"{l.kondisi:>8s} | {l.trust_score:>5.2f} | {round(b_norm,3):>6} | "
                f"{round(value,3):>6} | {round(final,3):>6} | {round(final*100)}%"
            )
