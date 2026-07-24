"""
Uji sensitivitas bobot FinalScore = alpha*BM25_norm + (1-alpha)*ValueScore
(alpha default 0,55).

BM25 hanya aktif kalau ada kueri, dan wizard produksi saat ini belum
menjaring kueri bebas. Command ini menyediakan kueri uji secara eksplisit
supaya bobot benar-benar bisa diuji, lalu menggeser alpha dari 0 ke 1 dan
menampilkan juara 1 pada tiap titik -- termasuk titik "flip" (saat juara 1
berganti), sebagai bukti bahwa bobot 0,55/0,45 bukan pilihan netral.

Jalankan:
    python manage.py weight_sensitivity
    python manage.py weight_sensitivity --query "iphone 13 pro 256gb mulus"
    python manage.py weight_sensitivity --seri "iPhone 13 Series" --varian pro --harga-max 9000000
"""
from django.core.management.base import BaseCommand

from engine.bm25_engine import BM25Engine
from engine.recommender import _filtered_listings, calculate_adaptive_weights
from engine.value_score import calculate as calculate_value_score

DEFAULT_ALPHAS = [0.0, 0.1, 0.2, 0.3, 0.35, 0.45, 0.55, 0.65, 0.75, 0.9, 1.0]
PAPER_ALPHA = 0.55


class Command(BaseCommand):
    help = (
        'Uji sensitivitas bobot BM25 vs ValueScore pada Persamaan 6 -- '
        'menampilkan matriks juara-1 untuk tiap nilai alpha dan titik flip-nya.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--seri', default='iPhone 12 Series')
        parser.add_argument('--varian', default='pro')
        parser.add_argument('--harga-max', type=int, default=7_000_000)
        parser.add_argument('--storage-min', type=int, default=128)
        parser.add_argument('--bh-min', type=int, default=85)
        parser.add_argument(
            '--query',
            default=None,
            help=(
                'Kueri uji untuk BM25. Jika tidak diisi, otomatis dibuat dari '
                'dokumen_teks kandidat dengan ValueScore TERENDAH di pool -- '
                'sengaja dipilih supaya ada pertentangan nyata antara skor '
                'teks dan skor preferensi (menunjukkan sensitivitas bobot).'
            ),
        )
        parser.add_argument(
            '--alphas',
            default=None,
            help='Daftar alpha dipisah koma, mis. "0,0.25,0.5,0.75,1". Default: 11 titik 0..1.',
        )

    def handle(self, *args, **options):
        session_data = {
            'seri': options['seri'],
            'varian': options['varian'],
            'harga_min': 0,
            'harga_max': options['harga_max'],
            'price_weight_zero': False,
            'storage_min': options['storage_min'],
            'bh_min': options['bh_min'],
            'kondisi_min': None,
            'garansi': None,
        }

        listings, relaxed = _filtered_listings(session_data)
        if not listings:
            raise SystemExit('Tidak ada kandidat yang lolos hard filter untuk skenario ini.')

        weights = calculate_adaptive_weights(session_data)
        value_scores = {l.id: calculate_value_score(l, weights) for l in listings}

        query = options['query']
        auto_query_note = None
        if not query:
            lowest = min(listings, key=lambda l: value_scores[l.id])
            query = lowest.dokumen_teks
            auto_query_note = lowest

        bm25 = BM25Engine.get_instance()
        ids = [l.id for l in listings]
        bm25_raw = bm25.score(query, ids)
        max_bm25 = max(bm25_raw.values()) if bm25_raw else 0.0
        bm25_norm = {
            lid: (score / max_bm25 if max_bm25 > 0 else 0.0)
            for lid, score in bm25_raw.items()
        }

        if options['alphas']:
            alphas = [float(a) for a in options['alphas'].split(',')]
        else:
            alphas = DEFAULT_ALPHAS
        if PAPER_ALPHA not in alphas:
            alphas = sorted(alphas + [PAPER_ALPHA])

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(
            '=== Uji Sensitivitas Bobot: FinalScore = alpha*BM25 + (1-alpha)*ValueScore ==='
        ))
        self.stdout.write(
            f"Skenario: {options['seri']} / {options['varian']}, "
            f"harga<=Rp{options['harga_max']:,}, storage>={options['storage_min']}GB, "
            f"BH>={options['bh_min']}%"
        )
        self.stdout.write(f'Kandidat lolos hard filter: {len(listings)}')
        if auto_query_note is not None:
            self.stdout.write(
                f'Kueri uji (otomatis, dari kandidat ValueScore terendah = '
                f'{round(value_scores[auto_query_note.id], 3)}): "{query}"'
            )
        else:
            self.stdout.write(f'Kueri uji (manual): "{query}"')
        self.stdout.write('')

        header = f"{'alpha(BM25)':>11} | {'beta(Value)':>11} | {'BM25':>6} | {'Value':>6} | {'Final':>6} | Juara 1"
        self.stdout.write(header)
        self.stdout.write('-' * len(header))

        previous_winner_id = None
        for alpha in alphas:
            beta = 1 - alpha
            winner = max(
                listings,
                key=lambda l: alpha * bm25_norm.get(l.id, 0.0) + beta * value_scores[l.id],
            )
            b = round(bm25_norm.get(winner.id, 0.0), 3)
            v = round(value_scores[winner.id], 3)
            f = round(alpha * b + beta * v, 3)
            flip_marker = ''
            if previous_winner_id is not None and winner.id != previous_winner_id:
                flip_marker = '  <-- FLIP'
            if abs(alpha - PAPER_ALPHA) < 1e-9:
                flip_marker += '  <-- BOBOT DI PAPER'
            label = f'{winner.kategori_varian} {winner.penyimpanan} Rp{winner.harga:,} BH{winner.battery_health:.0f}% {winner.kondisi}'
            self.stdout.write(
                f"{alpha:>11.2f} | {beta:>11.2f} | {b:>6} | {v:>6} | {f:>6} | {label}{flip_marker}"
            )
            previous_winner_id = winner.id

        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            'Catatan: baris "<-- FLIP" menandai titik saat juara-1 berganti akibat '
            'pergeseran bobot alpha. Bandingkan posisi "BOBOT DI PAPER" (alpha=0,55) '
            'terhadap titik flip untuk menilai apakah bobot itu netral atau condong '
            'ke salah satu sisi (BM25 vs ValueScore).'
        ))
