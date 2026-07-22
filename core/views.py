from django.shortcuts import redirect, render

from core.models import IphoneListing
from engine.intent_detector import detect_intent
from engine.recommender import get_recommendations
from engine.value_score import BUDGET_FIRST_WEIGHTS, SPEC_FIRST_WEIGHTS

SERI_OPTIONS = [
    'iPhone 11 Series',
    'iPhone 12 Series',
    'iPhone 13 Series',
    'iPhone 14 Series',
    'iPhone 15 Series',
]

STORAGE_OPTIONS = [64, 128, 256, 512]

KONDISI_OPTIONS = [
    ('normal', 'Normal'),
    ('mulus', 'Mulus'),
    ('like_new', 'Like New'),
]
KONDISI_LABEL = dict(KONDISI_OPTIONS)

TOTAL_STEPS = 5


def index(request):
    return render(request, 'index.html')


def wizard_start(request):
    if request.method != 'POST':
        return redirect('index')

    query = request.POST.get('query', '').strip()
    if not query:
        return redirect('index')

    request.session['wizard'] = {'query': query}
    request.session.modified = True
    return redirect('wizard_step', step=1)


def wizard_step(request, step):
    wizard_data = request.session.get('wizard')
    if not wizard_data:
        return redirect('index')

    if step < 1 or step > TOTAL_STEPS:
        return redirect('index')

    if request.method == 'POST':
        _save_step(request, step, wizard_data)
        request.session['wizard'] = wizard_data
        request.session.modified = True

        if step == TOTAL_STEPS:
            return _run_engine_and_redirect(request, wizard_data)
        return redirect('wizard_step', step=step + 1)

    context = _build_step_context(step, wizard_data)
    return render(request, 'wizard.html', context)


def _save_step(request, step, wizard_data):
    if step == 1:
        wizard_data['seri'] = request.POST.get('seri') or None
    elif step == 2:
        storage_min = request.POST.get('storage_min')
        wizard_data['storage_min'] = int(storage_min) if storage_min else None
    elif step == 3:
        bh_min = request.POST.get('bh_min')
        wizard_data['bh_min'] = int(bh_min) if bh_min else None
    elif step == 4:
        wizard_data['kondisi_min'] = request.POST.get('kondisi_min') or None
    # step 5 = halaman konfirmasi, tidak ada input baru untuk disimpan


def _build_step_context(step, wizard_data):
    context = {
        'step': step,
        'total_steps': TOTAL_STEPS,
        'step_range': range(1, TOTAL_STEPS + 1),
        'query': wizard_data.get('query', ''),
        'prev_step': step - 1,
    }

    if step == 1:
        context['seri_options'] = SERI_OPTIONS
        context['selected_seri'] = wizard_data.get('seri')
    elif step == 2:
        context['storage_options'] = STORAGE_OPTIONS
        context['selected_storage'] = wizard_data.get('storage_min')
    elif step == 3:
        context['selected_bh'] = wizard_data.get('bh_min', 0)
    elif step == 4:
        context['kondisi_options'] = KONDISI_OPTIONS
        context['selected_kondisi'] = wizard_data.get('kondisi_min')
    elif step == 5:
        context['summary'] = _build_summary(wizard_data)

    return context


def _build_summary(wizard_data):
    return {
        'Query': wizard_data.get('query') or '-',
        'Seri': wizard_data.get('seri') or 'Semua seri',
        'Storage minimum': (
            f"{wizard_data['storage_min']}GB" if wizard_data.get('storage_min') else 'Tidak masalah'
        ),
        'Battery Health minimum': (
            f"{wizard_data['bh_min']}%" if wizard_data.get('bh_min') else 'Tidak masalah'
        ),
        'Kondisi minimum': KONDISI_LABEL.get(wizard_data.get('kondisi_min'), 'Tidak masalah'),
    }


def _run_engine_and_redirect(request, wizard_data):
    query = wizard_data.get('query', '')
    intent = detect_intent(query)
    mode = intent['mode']
    weights = BUDGET_FIRST_WEIGHTS if mode == 'budget_first' else SPEC_FIRST_WEIGHTS

    session_data = {
        'query': query,
        'mode': mode,
        'seri': wizard_data.get('seri'),
        'storage_min': wizard_data.get('storage_min'),
        'bh_min': wizard_data.get('bh_min'),
        'kondisi_min': wizard_data.get('kondisi_min'),
        'intent_signals': intent['signals'],
        'weights': weights,
    }

    results = get_recommendations(session_data)

    request.session['result_ids'] = [r['listing'].id for r in results]
    request.session['result_meta'] = {
        str(r['listing'].id): {
            'bm25_score': r['bm25_score'],
            'value_score': r['value_score'],
            'final_score': r['final_score'],
            'match_percent': r['match_percent'],
            'reason': r['reason'],
        }
        for r in results
    }
    request.session['wizard_summary'] = _build_summary(wizard_data)
    request.session['wizard_query'] = query
    request.session['wizard_mode'] = mode
    request.session.modified = True

    return redirect('result')


def result(request):
    result_ids = request.session.get('result_ids')
    if not result_ids:
        return redirect('index')

    result_meta = request.session.get('result_meta', {})
    listings = {listing.id: listing for listing in IphoneListing.objects.filter(id__in=result_ids)}

    recommendations = []
    for idx, lid in enumerate(result_ids, start=1):
        listing = listings.get(lid)
        if not listing:
            continue
        meta = result_meta.get(str(lid), {})
        harga_str = f'{listing.harga:,}'.replace(',', '.')
        bh_rounded = round(listing.battery_health) if listing.battery_health is not None else 0
        recommendations.append({
            'rank': idx,
            'listing': listing,
            'harga_str': harga_str,
            'bh_rounded': bh_rounded,
            **meta,
        })

    context = {
        'recommendations': recommendations,
        'query': request.session.get('wizard_query', ''),
        'mode': request.session.get('wizard_mode', ''),
        'summary': request.session.get('wizard_summary', {}),
    }
    return render(request, 'result.html', context)


def restart(request):
    request.session.flush()
    return redirect('index')
