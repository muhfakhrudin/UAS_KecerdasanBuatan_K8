from django.shortcuts import redirect, render

from core.models import IphoneListing
from engine.recommender import get_recommendations_detailed

TOTAL_STEPS = 8

# --- Step 1: Seri -----------------------------------------------------
SERI_OPTIONS = [
    ('iPhone 11 Series', 'iPhone 11', 'Rp 3–7 juta · Solid & terjangkau'),
    ('iPhone 12 Series', 'iPhone 12', 'Rp 5–9 juta · 5G ready'),
    ('iPhone 13 Series', 'iPhone 13', 'Rp 6–12 juta · Kamera terbaik di kelasnya'),
    ('iPhone 14 Series', 'iPhone 14', 'Rp 9–16 juta · Crash Detection'),
    ('iPhone 15 Series', 'iPhone 15', 'Rp 12–20 juta · USB-C & kamera 48MP'),
]
SERI_LABEL = {value: label for value, label, _ in SERI_OPTIONS}

# --- Step 2: Varian Model ----------------------------------------------
VARIAN_OPTIONS = [
    ('reguler', 'Reguler', 'Ukuran standar, harga terjangkau'),
    ('mini', 'Mini', 'Layar 5.4", genggaman nyaman'),
    ('plus', 'Plus', 'Baterai besar, layar lebar'),
    ('pro', 'Pro', 'Kamera pro, chipset tertinggi'),
    ('pro_max', 'Pro Max', 'Layar terbesar, performa maksimal'),
]
VARIAN_LABEL = {value: label for value, label, _ in VARIAN_OPTIONS}

# Mini hanya ada di seri 12 & 13. Plus hanya ada di seri 14 & 15.
VARIAN_UNAVAILABLE = {
    'iPhone 11 Series': {'mini', 'plus'},
    'iPhone 12 Series': {'plus'},
    'iPhone 13 Series': {'plus'},
    'iPhone 14 Series': {'mini'},
    'iPhone 15 Series': {'mini'},
}

# --- Step 3: Range Harga -------------------------------------------------
HARGA_OPTIONS = [
    ('lt4', 'Di bawah Rp 4 juta', 'iPhone 11 atau 12 standar', 0, 4_000_000),
    ('4-6', 'Rp 4–6 juta', 'iPhone 11 Pro / 12 standar', 4_000_000, 6_000_000),
    ('6-9', 'Rp 6–9 juta', 'iPhone 12 Pro / 13 standar', 6_000_000, 9_000_000),
    ('9-13', 'Rp 9–13 juta', 'iPhone 13 Pro / 14 standar', 9_000_000, 13_000_000),
    ('13-18', 'Rp 13–18 juta', 'iPhone 14 Pro / 15 standar', 13_000_000, 18_000_000),
    ('gt18', 'Di atas Rp 18 juta', 'iPhone 15 Pro Max', 18_000_000, 999_999_999),
]
HARGA_MAP = {key: (label, lo, hi) for key, label, _, lo, hi in HARGA_OPTIONS}
HARGA_ANY_KEY = 'any'

# --- Step 4: Kapasitas Penyimpanan ---------------------------------------
STORAGE_OPTIONS = [
    (64, '64 GB', 'Cukup untuk pemakaian ringan'),
    (128, '128 GB', 'Paling populer, serba cukup'),
    (256, '256 GB', 'Foto & video banyak'),
    (512, '512 GB', 'Kreator konten'),
    (1024, '1 TB', 'Maksimal, tanpa kompromi'),
]

# --- Step 5: Battery Health Minimum --------------------------------------
BH_OPTIONS = [
    (90, '90% ke atas', 'Kondisi hampir baru, baterai prima'),
    (85, '85% ke atas', 'Standar aman, masih nyaman harian'),
    (80, '80% ke atas', 'Masih layak, harga lebih terjangkau'),
]

# --- Step 6: Kondisi Fisik -----------------------------------------------
KONDISI_OPTIONS = [
    ('like_new', 'Like New', 'Tidak ada goresan, seperti baru dibuka'),
    ('mulus', 'Mulus', 'Goresan sangat minimal, fullset'),
    ('normal', 'Normal', 'Bekas pakai normal, fungsional sempurna'),
]
KONDISI_LABEL = {value: label for value, label, _ in KONDISI_OPTIONS}

# --- Step 7: Status Garansi -----------------------------------------------
GARANSI_OPTIONS = [
    ('resmi', 'Garansi Resmi (iBox)', 'iBox official, klaim mudah di Indonesia'),
    ('inter', 'Garansi Inter (International)', 'Garansi global Apple, bisa klaim di Apple Store'),
    ('beacukai', 'Beacukai', 'Sudah legal, harga lebih terjangkau'),
    ('tidak_ada', 'Tidak Ada Garansi', 'Harga paling terjangkau, beli as-is'),
]
GARANSI_LABEL = {value: label for value, label, _ in GARANSI_OPTIONS}


def index(request):
    return render(request, 'index.html')


def wizard_start(request):
    if request.method != 'POST':
        return redirect('index')

    request.session['wizard'] = {'_step_reached': 1}
    request.session.modified = True
    return redirect('wizard_step', step=1)


def wizard_step(request, step):
    wizard_data = request.session.get('wizard')
    if wizard_data is None:
        return redirect('index')

    if step < 1 or step > TOTAL_STEPS:
        return redirect('index')

    step_reached = wizard_data.get('_step_reached', 1)
    if step > step_reached:
        return redirect('wizard_step', step=step_reached)

    if request.method == 'POST':
        _save_step(request, step, wizard_data)
        wizard_data['_step_reached'] = max(step_reached, min(step + 1, TOTAL_STEPS))
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
        wizard_data['varian_relaxed_msg'] = None

    elif step == 2:
        varian = request.POST.get('varian') or None
        seri = wizard_data.get('seri')
        if varian and seri and varian in VARIAN_UNAVAILABLE.get(seri, set()):
            wizard_data['varian_relaxed_msg'] = (
                f'{SERI_LABEL.get(seri, seri)} {VARIAN_LABEL.get(varian, varian)} tidak tersedia. '
                f'Menampilkan semua varian {SERI_LABEL.get(seri, seri)}.'
            )
            varian = None
        else:
            wizard_data['varian_relaxed_msg'] = None
        wizard_data['varian'] = varian

    elif step == 3:
        harga_key = request.POST.get('harga') or HARGA_ANY_KEY
        wizard_data['harga_key'] = harga_key
        if harga_key == HARGA_ANY_KEY:
            wizard_data['harga_min'] = 0
            wizard_data['harga_max'] = 999_999_999
            wizard_data['price_weight_zero'] = True
        else:
            _, lo, hi = HARGA_MAP.get(harga_key, ('', 0, 999_999_999))
            wizard_data['harga_min'] = lo
            wizard_data['harga_max'] = hi
            wizard_data['price_weight_zero'] = False

    elif step == 4:
        storage_min = request.POST.get('storage_min')
        wizard_data['storage_min'] = int(storage_min) if storage_min else None

    elif step == 5:
        bh_min = request.POST.get('bh_min')
        wizard_data['bh_min'] = int(bh_min) if bh_min else None

    elif step == 6:
        wizard_data['kondisi_min'] = request.POST.get('kondisi_min') or None

    elif step == 7:
        wizard_data['garansi'] = request.POST.get('garansi') or None
    # step 8 = halaman konfirmasi, tidak ada input baru untuk disimpan


def _build_step_context(step, wizard_data):
    context = {
        'step': step,
        'total_steps': TOTAL_STEPS,
        'step_range': range(1, TOTAL_STEPS + 1),
        'prev_step': step - 1,
    }

    if step == 1:
        context['seri_options'] = SERI_OPTIONS
        context['selected_seri'] = wizard_data.get('seri')
    elif step == 2:
        context['varian_options'] = VARIAN_OPTIONS
        context['selected_varian'] = wizard_data.get('varian')
        context['relaxed_msg'] = wizard_data.get('varian_relaxed_msg')
    elif step == 3:
        context['harga_options'] = HARGA_OPTIONS
        context['selected_harga'] = wizard_data.get('harga_key')
        context['harga_any_key'] = HARGA_ANY_KEY
    elif step == 4:
        context['storage_options'] = STORAGE_OPTIONS
        context['selected_storage'] = wizard_data.get('storage_min')
    elif step == 5:
        context['bh_options'] = BH_OPTIONS
        context['selected_bh'] = wizard_data.get('bh_min')
    elif step == 6:
        context['kondisi_options'] = KONDISI_OPTIONS
        context['selected_kondisi'] = wizard_data.get('kondisi_min')
    elif step == 7:
        context['garansi_options'] = GARANSI_OPTIONS
        context['selected_garansi'] = wizard_data.get('garansi')
    elif step == 8:
        context['summary'] = _build_summary(wizard_data)

    return context


def _build_summary(wizard_data):
    seri = wizard_data.get('seri')
    varian = wizard_data.get('varian')
    harga_key = wizard_data.get('harga_key')
    storage_min = wizard_data.get('storage_min')
    bh_min = wizard_data.get('bh_min')
    kondisi_min = wizard_data.get('kondisi_min')
    garansi = wizard_data.get('garansi')

    harga_label = 'Tidak ada batasan'
    if harga_key and harga_key != HARGA_ANY_KEY:
        harga_label = HARGA_MAP.get(harga_key, (harga_key, 0, 0))[0]

    return {
        'Seri': SERI_LABEL.get(seri, 'Semua seri'),
        'Varian': VARIAN_LABEL.get(varian, 'Semua varian'),
        'Budget': harga_label,
        'Penyimpanan': f'{storage_min}GB+' if storage_min else 'Tidak masalah',
        'Battery Health': f'{bh_min}% ke atas' if bh_min else 'Tidak masalah',
        'Kondisi': KONDISI_LABEL.get(kondisi_min, 'Tidak masalah'),
        'Garansi': GARANSI_LABEL.get(garansi, 'Tidak masalah'),
    }


def _run_engine_and_redirect(request, wizard_data):
    session_data = {
        'seri': wizard_data.get('seri'),
        'varian': wizard_data.get('varian'),
        'harga_min': wizard_data.get('harga_min', 0),
        'harga_max': wizard_data.get('harga_max', 999_999_999),
        'price_weight_zero': wizard_data.get('price_weight_zero', False),
        'storage_min': wizard_data.get('storage_min'),
        'bh_min': wizard_data.get('bh_min'),
        'kondisi_min': wizard_data.get('kondisi_min'),
        'garansi': wizard_data.get('garansi'),
    }

    outcome = get_recommendations_detailed(session_data)

    request.session['result_ids'] = [r['listing'].id for r in outcome['results']]
    request.session['result_meta'] = {
        str(r['listing'].id): {
            'bm25_score': r['bm25_score'],
            'value_score': r['value_score'],
            'final_score': r['final_score'],
            'match_percent': r['match_percent'],
            'reason': r['reason'],
        }
        for r in outcome['results']
    }
    request.session['wizard_summary'] = _build_summary(wizard_data)
    request.session['wizard_relaxed'] = outcome['relaxed']
    request.session.modified = True

    return redirect('result')


def result(request):
    result_ids = request.session.get('result_ids')
    if result_ids is None:
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
        'summary': request.session.get('wizard_summary', {}),
        'relaxed': request.session.get('wizard_relaxed', False),
    }
    return render(request, 'result.html', context)


def restart(request):
    request.session.flush()
    return redirect('index')
