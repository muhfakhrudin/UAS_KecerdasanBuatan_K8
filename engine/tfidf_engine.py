"""Utility TF-IDF untuk menghitung cosine similarity antara query dan dokumen."""

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def compute_similarity(query: str, documents: list) -> list:
    """Hitung cosine similarity TF-IDF antara query dan tiap dokumen di `documents`."""
    corpus = documents + [query]

    vectorizer = TfidfVectorizer()
    try:
        matrix = vectorizer.fit_transform(corpus)
    except ValueError:
        # Query/dokumen tidak mengandung token yang dikenali vectorizer
        return [0.0] * len(documents)

    query_vector = matrix[-1]
    doc_vectors = matrix[:-1]
    similarities = cosine_similarity(query_vector, doc_vectors)[0]
    return [float(s) for s in similarities]
