from django.db import models


class IphoneListing(models.Model):
    KONDISI_CHOICES = [
        ('like_new', 'Like New'),
        ('mulus', 'Mulus'),
        ('normal', 'Normal'),
        ('bekas', 'Bekas'),
        ('unknown', 'Unknown'),
    ]

    # Data asli dari CSV
    platform = models.CharField(max_length=50)
    nama_toko = models.CharField(max_length=200)
    rating_produk = models.FloatField(default=0.0)
    has_rating = models.BooleanField(default=False)
    produk_terjual = models.IntegerField(default=0)
    kategori_seri = models.CharField(max_length=100)
    kategori_varian = models.CharField(max_length=100)
    penyimpanan = models.CharField(max_length=20)
    battery_health = models.FloatField(null=True, blank=True)
    bh_imputed = models.BooleanField(default=False)
    harga = models.BigIntegerField()
    wilayah_toko = models.CharField(max_length=100)
    link_pembelian = models.URLField(max_length=2000)

    # Kolom hasil engineering
    kondisi = models.CharField(max_length=50, choices=KONDISI_CHOICES, default='unknown')
    generasi = models.IntegerField()
    is_pro = models.BooleanField(default=False)
    penyimpanan_gb = models.IntegerField(default=128)

    # Teks gabungan untuk BM25 indexing
    dokumen_teks = models.TextField()

    # Trust score (dihitung saat load data)
    trust_score = models.FloatField(default=0.0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-trust_score', '-battery_health']

    def __str__(self):
        return f"{self.kategori_varian} {self.penyimpanan} - {self.harga}"
