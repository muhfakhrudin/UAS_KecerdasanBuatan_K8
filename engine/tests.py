"""
Unit test nyata (Django TestCase, dijalankan lewat `python manage.py test`)
untuk komponen inti AI engine: fuzzy_engine, value_score, dan recommender.

Sebelumnya satu-satunya test untuk engine adalah `test_engine.py`, sebuah
script manual yang menguji jalur free-text query dari desain lama dan tidak
pernah dijalankan otomatis. File ini menutup gap tersebut dengan test yang
benar-benar tereksekusi oleh test runner dan mencakup jalur yang sungguhan
dipakai wizard sekarang (termasuk BM25 yang kini bisa aktif lewat field query
opsional di step 9).
"""

from django.test import TestCase

from core.models import IphoneListing
from engine.bm25_engine import BM25Engine
from engine.fuzzy_engine import infer_quality
from engine.recommender import calculate_adaptive_weights, get_recommendations_detailed
from engine.value_score import calculate as calculate_value_score, clear_harga_bounds_cache


class FuzzyEngineTests(TestCase):
    """FIS Mamdani: fuzzifikasi -> agregasi rule -> defuzzifikasi centroid."""

    def test_low_inputs_yield_low_quality(self):
        score = infer_quality(bh=0, price_eff=0.0, trust=0.0)
        self.assertLess(score, 0.35)

    def test_high_inputs_yield_high_quality(self):
        score = infer_quality(bh=100, price_eff=1.0, trust=1.0)
        self.assertGreater(score, 0.7)

    def test_mid_inputs_yield_mid_quality(self):
        score = infer_quality(bh=80, price_eff=0.5, trust=0.5)
        self.assertTrue(0.3 <= score <= 0.7)

    def test_battery_health_is_monotonic_at_fixed_price_and_trust(self):
        """Menaikkan BH saja (price/trust tetap) tidak boleh menurunkan skor --
        properti dasar yang wajib dipenuhi rule base manapun."""
        low_bh = infer_quality(bh=60, price_eff=0.5, trust=0.5)
        high_bh = infer_quality(bh=95, price_eff=0.5, trust=0.5)
        self.assertGreaterEqual(high_bh, low_bh)

    def test_trapezoid_plateau_edge_case(self):
        """BH_SETS['tinggi'] = trapezoid(x, 85, 95, 100, 100) -- domain mentok
        di 100 (c == d). x == 100 harus tetap keanggotaan penuh (1.0), bukan
        dianggap di luar himpunan seperti disebutkan di komentar fuzzy_engine.py.
        Diverifikasi lewat efeknya: BH=100 dengan price/trust rendah tetap
        harus menang telak dibanding BH=0 pada kondisi yang sama."""
        bh_100 = infer_quality(bh=100, price_eff=0.0, trust=0.0)
        bh_0 = infer_quality(bh=0, price_eff=0.0, trust=0.0)
        self.assertGreater(bh_100, bh_0)


def _make_listing(**overrides):
    defaults = dict(
        platform='tokopedia',
        nama_toko='Toko Uji',
        rating_produk=4.8,
        has_rating=True,
        produk_terjual=50,
        kategori_seri='iPhone 12 Series',
        kategori_varian='iPhone 12',
        penyimpanan='128GB',
        battery_health=85.0,
        bh_imputed=False,
        harga=6_000_000,
        wilayah_toko='Jakarta',
        link_pembelian='https://tokopedia.com/contoh',
        kondisi='mulus',
        generasi=12,
        is_pro=False,
        penyimpanan_gb=128,
        varian_model='reguler',
        garansi='resmi',
        dokumen_teks='iphone 12 128gb mulus battery health 85 kamera bagus',
        trust_score=0.8,
    )
    defaults.update(overrides)
    return IphoneListing.objects.create(**defaults)


class ValueScoreTests(TestCase):
    def setUp(self):
        clear_harga_bounds_cache()

    def test_missing_battery_health_treated_as_zero_not_error(self):
        listing = _make_listing(battery_health=None)
        weights = {'bh': 0.35, 'gen': 0.30, 'kondisi': 0.20, 'price': 0.0, 'trust': 0.15}
        score = calculate_value_score(listing, weights)
        self.assertGreaterEqual(score, 0.0)

    def test_better_listing_scores_higher_under_equal_weights(self):
        # Beberapa listing lain diperlukan supaya percentile harga (_harga_bounds)
        # punya rentang yang berarti.
        for harga in (2_000_000, 4_000_000, 8_000_000, 10_000_000, 12_000_000):
            _make_listing(harga=harga, battery_health=70, kondisi='normal', generasi=11)

        better = _make_listing(
            harga=3_000_000, battery_health=98, kondisi='like_new', generasi=15, trust_score=0.95,
        )
        worse = _make_listing(
            harga=11_000_000, battery_health=70, kondisi='bekas', generasi=11, trust_score=0.2,
        )

        weights = {'bh': 0.30, 'gen': 0.25, 'kondisi': 0.20, 'price': 0.15, 'trust': 0.10}
        self.assertGreater(
            calculate_value_score(better, weights),
            calculate_value_score(worse, weights),
        )

    def test_score_is_clamped_between_zero_and_one(self):
        listing = _make_listing(battery_health=100, kondisi='like_new', generasi=15, trust_score=1.0)
        weights = {'bh': 0.35, 'gen': 0.30, 'kondisi': 0.20, 'price': 0.0, 'trust': 0.15}
        score = calculate_value_score(listing, weights)
        self.assertTrue(0.0 <= score <= 1.0)


class AdaptiveWeightsTests(TestCase):
    def test_weights_always_sum_to_one(self):
        scenarios = [
            {},
            {'priority': 'bh'},
            {'priority': 'trust'},
            {'price_weight_zero': True},
            {'varian': 'pro_max'},
            {'garansi': 'resmi'},
            {'priority': 'price', 'garansi': 'resmi', 'varian': 'pro'},
        ]
        for session_data in scenarios:
            weights = calculate_adaptive_weights(session_data)
            self.assertAlmostEqual(sum(weights.values()), 1.0, places=6, msg=session_data)

    def test_priority_dimension_gets_boosted(self):
        weights = calculate_adaptive_weights({'priority': 'trust'})
        self.assertEqual(weights['trust'], max(weights.values()))

    def test_price_weight_zero_removes_price_dimension(self):
        weights = calculate_adaptive_weights({'price_weight_zero': True})
        self.assertEqual(weights['price'], 0.0)


class RecommenderTests(TestCase):
    def setUp(self):
        clear_harga_bounds_cache()
        BM25Engine.reset_instance()

    def tearDown(self):
        BM25Engine.reset_instance()

    def test_empty_query_gives_final_score_equal_to_value_score(self):
        """Menutup gap yang ditemukan review: saat wizard tidak mengisi query,
        BM25 harus benar-benar tidak aktif dan FinalScore harus 100% ValueScore
        (bukan diam-diam terpotong ke rentang 0..0.45)."""
        _make_listing(kategori_seri='iPhone 12 Series')
        _make_listing(kategori_seri='iPhone 12 Series', harga=7_000_000, battery_health=95)

        outcome = get_recommendations_detailed({'seri': 'iPhone 12 Series', 'query': ''})
        for r in outcome['results']:
            self.assertEqual(r['bm25_score'], 0.0)
            self.assertEqual(r['final_score'], r['value_score'])

    def test_query_matching_one_listing_activates_bm25(self):
        """Field query opsional di step 9 harus benar-benar menyalakan BM25,
        bukan cuma dihitung lalu dibuang seperti detect_intent()."""
        target = _make_listing(
            kategori_seri='iPhone 13 Series',
            dokumen_teks='iphone 13 pro kamera fotografi profesional malam hari terbaik',
        )
        # BM25's classic IDF (log(N-n+0.5) - log(n+0.5)) is exactly zero when a
        # term's document frequency n is precisely half the corpus size N --
        # e.g. N=2, n=1 -> log(1.5)-log(1.5)=0. A couple of unrelated filler
        # listings keeps the query terms' document frequency below N/2 so IDF
        # (and therefore the BM25 score) comes out meaningfully positive.
        for _ in range(3):
            _make_listing(
                kategori_seri='iPhone 13 Series',
                dokumen_teks='iphone 13 reguler baterai awet harian biasa saja',
            )

        outcome = get_recommendations_detailed({
            'seri': 'iPhone 13 Series',
            'query': 'kamera fotografi profesional',
        })

        winner = outcome['results'][0]
        self.assertEqual(winner['listing'].id, target.id)
        self.assertGreater(winner['bm25_score'], 0.0)

    def test_hard_filter_excludes_non_matching_series(self):
        _make_listing(kategori_seri='iPhone 12 Series')
        _make_listing(kategori_seri='iPhone 14 Series')

        outcome = get_recommendations_detailed({'seri': 'iPhone 14 Series', 'query': ''})
        series_in_results = {r['listing'].kategori_seri for r in outcome['results']}
        self.assertEqual(series_in_results, {'iPhone 14 Series'})

    def test_relaxes_kondisi_and_garansi_when_no_candidates_match(self):
        _make_listing(kategori_seri='iPhone 12 Series', kondisi='bekas', garansi='tidak_ada')

        outcome = get_recommendations_detailed({
            'seri': 'iPhone 12 Series',
            'kondisi_min': 'like_new',
            'garansi': 'resmi',
            'query': '',
        })

        self.assertTrue(outcome['relaxed'])
        self.assertEqual(len(outcome['results']), 1)

    def test_no_candidates_at_all_returns_empty_without_error(self):
        outcome = get_recommendations_detailed({'seri': 'iPhone 15 Series', 'query': ''})
        self.assertEqual(outcome['results'], [])
