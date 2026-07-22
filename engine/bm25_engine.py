"""
BM25 engine untuk re-ranking listing berdasarkan relevansi teks.
Menggunakan rank_bm25 library.

Alur:
1. Saat startup (lazy, sekali per proses): index semua dokumen_teks dari database
2. Saat query: tokenize query -> hitung BM25 score -> return scores per listing
"""

from rank_bm25 import BM25Okapi

STOPWORDS_ID = {'yang', 'dan', 'di', 'ke', 'dari', 'untuk', 'ini', 'itu'}


def tokenize(text: str) -> list:
    return [t for t in (text or '').lower().split() if t not in STOPWORDS_ID]


class BM25Engine:
    _instance = None

    def __init__(self):
        from core.models import IphoneListing

        listings = list(IphoneListing.objects.only('id', 'dokumen_teks'))
        self.ids = [listing.id for listing in listings]
        corpus_tokens = [tokenize(listing.dokumen_teks) for listing in listings]
        self.bm25 = BM25Okapi(corpus_tokens) if corpus_tokens else None

    @classmethod
    def get_instance(cls) -> 'BM25Engine':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        cls._instance = None

    def score(self, query: str, listing_ids: list) -> dict:
        if not self.bm25:
            return {lid: 0.0 for lid in listing_ids}

        tokens = tokenize(query)
        if not tokens:
            return {lid: 0.0 for lid in listing_ids}

        scores = self.bm25.get_scores(tokens)
        id_to_score = dict(zip(self.ids, scores))
        return {lid: float(id_to_score.get(lid, 0.0)) for lid in listing_ids}
