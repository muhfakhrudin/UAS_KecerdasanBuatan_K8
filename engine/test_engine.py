"""
Script test manual untuk AI engine (bukan Django TestCase, dijalankan langsung
lewat `python manage.py shell < engine/test_engine.py` atau sebagai module biasa
setelah django.setup()).
"""

import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartpick.settings')
django.setup()

from engine.intent_detector import detect_intent  # noqa: E402
from engine.recommender import get_recommendations  # noqa: E402


def test_spec_first():
    intent = detect_intent('mau yang terbaik tidak peduli harga')
    session_data = {
        'query': 'mau yang terbaik tidak peduli harga',
        'mode': 'spec_first',
        'seri': None,
        'storage_min': None,
        'bh_min': None,
        'kondisi_min': None,
        'intent_signals': intent['signals'],
    }
    result = get_recommendations(session_data)

    assert len(result) == 3, f'Expected 3 hasil, dapat {len(result)}'
    assert result[0]['final_score'] >= result[1]['final_score'] >= result[2]['final_score'], (
        'Hasil rekomendasi harus terurut dari skor tertinggi ke terendah'
    )
    print('test_spec_first OK ->', [r['listing'].kategori_varian for r in result])


def test_budget_first():
    query = 'mau yang murah tapi bagus'
    intent = detect_intent(query)
    assert intent['mode'] == 'budget_first', f"Intent seharusnya budget_first, dapat {intent['mode']}"

    from engine.value_score import BUDGET_FIRST_WEIGHTS

    assert BUDGET_FIRST_WEIGHTS['price'] > 0, 'Bobot price harus > 0 pada mode budget_first'

    session_data = {
        'query': query,
        'mode': 'budget_first',
        'seri': None,
        'storage_min': None,
        'bh_min': None,
        'kondisi_min': None,
        'intent_signals': intent['signals'],
    }
    result = get_recommendations(session_data)

    assert len(result) == 3, f'Expected 3 hasil, dapat {len(result)}'
    print('test_budget_first OK ->', [r['listing'].kategori_varian for r in result])


def test_dialog_changes_result():
    query = 'mau iphone kamera terbaik'

    result_a = get_recommendations({'query': query, 'mode': 'spec_first'})
    result_b = get_recommendations({
        'query': query,
        'mode': 'spec_first',
        'seri': 'iPhone 11 Series',
    })

    ids_a = [r['listing'].id for r in result_a]
    ids_b = [r['listing'].id for r in result_b]

    assert ids_a != ids_b, 'Jawaban dialog berbeda seharusnya menghasilkan rekomendasi berbeda'
    print('test_dialog_changes_result OK -> A:', ids_a, 'B:', ids_b)


if __name__ == '__main__':
    test_spec_first()
    test_budget_first()
    test_dialog_changes_result()
    print('\nSemua test engine PASSED.')
