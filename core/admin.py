from django.contrib import admin

from core.models import IphoneListing


@admin.register(IphoneListing)
class IphoneListingAdmin(admin.ModelAdmin):
    list_display = (
        'kategori_varian',
        'penyimpanan',
        'harga',
        'battery_health',
        'kondisi',
        'trust_score',
        'platform',
    )
    list_filter = ('kategori_seri', 'penyimpanan', 'kondisi', 'platform')
    search_fields = ('nama_toko', 'kategori_varian')
