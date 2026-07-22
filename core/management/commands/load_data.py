import math
import re

import pandas as pd
from django.core.management.base import BaseCommand, CommandError

from core.models import IphoneListing

KONDISI_MAP = {
    'like_new': ['like new', 'likenew', 'like-new', 'baru'],
    'mulus': ['mulus', 'fullset', 'lengkap', 'no minus'],
    'normal': ['normal', 'second', 'bekas', 'eks'],
    'bekas': ['minus', 'cacat', 'retak', 'pecah'],
}

GARANSI_MAP = {
    'resmi': ['ibox', 'resmi', 'garansi resmi', 'official'],
    'inter': ['inter', 'international', 'garansi inter'],
    'beacukai': ['beacukai', 'bea cukai', ' bc '],
    'tidak_ada': ['no garansi', 'tanpa garansi', 'as is'],
}

STOPWORDS_ID = {'yang', 'dan', 'di', 'ke', 'dari', 'untuk', 'ini', 'itu'}


def parse_harga(value):
    digits = re.sub(r'[^0-9]', '', str(value))
    return int(digits) if digits else 0


def normalize_storage(value):
    value = str(value).strip().upper()
    if value == '126GB':
        value = '128GB'
    if value in ('1000GB', '1024GB'):
        return '1TB', 1024
    if value.endswith('TB'):
        num = float(value.replace('TB', ''))
        return f'{int(num)}TB', int(num * 1024)
    if value.endswith('GB'):
        gb = int(value.replace('GB', ''))
        return f'{gb}GB', gb
    return value, 128


def extract_generasi(kategori_seri):
    match = re.search(r'(\d+)', str(kategori_seri))
    return int(match.group(1)) if match else 0


def extract_kondisi(varian, link):
    haystack = f'{varian} {link}'.lower()
    for kondisi, keywords in KONDISI_MAP.items():
        for kw in keywords:
            if kw in haystack:
                return kondisi
    return 'unknown'


def extract_varian_model(kategori_varian):
    label = str(kategori_varian).lower()
    if 'pro max' in label:
        return 'pro_max'
    if 'pro' in label:
        return 'pro'
    if 'mini' in label:
        return 'mini'
    if 'plus' in label:
        return 'plus'
    return 'reguler'


def extract_garansi(varian, link):
    haystack = f'{varian} {link}'.lower()
    for garansi, keywords in GARANSI_MAP.items():
        for kw in keywords:
            if kw in haystack:
                return garansi
    return 'tidak_ada'


class Command(BaseCommand):
    help = 'Load dan preprocessing data listing iPhone dari file CSV ke database.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default='data/data_iphone_v2.csv',
            help='Path ke file CSV dataset.',
        )

    def handle(self, *args, **options):
        file_path = options['file']

        try:
            df = pd.read_csv(file_path)
        except FileNotFoundError:
            raise CommandError(f'File tidak ditemukan: {file_path}')

        self.stdout.write(f'Membaca {len(df)} baris dari {file_path}...')

        # --- Preprocessing dasar ---
        df['harga_int'] = df['Harga'].apply(parse_harga)

        storage_pairs = df['penyimpanan'].apply(normalize_storage)
        df['penyimpanan_norm'] = storage_pairs.apply(lambda x: x[0])
        df['penyimpanan_gb'] = storage_pairs.apply(lambda x: x[1])

        df['generasi'] = df['Kategori Seri'].apply(extract_generasi)
        df['is_pro'] = df['Kategori Varian'].str.contains('Pro', case=False, na=False)

        df['kondisi'] = df.apply(
            lambda row: extract_kondisi(row['Kategori Varian'], row['Link Pembelian']),
            axis=1,
        )

        df['varian_model'] = df['Kategori Varian'].apply(extract_varian_model)

        df['garansi'] = df.apply(
            lambda row: extract_garansi(row['Kategori Varian'], row['Link Pembelian']),
            axis=1,
        )

        df['has_rating'] = df['Rating Produk'] > 0

        # Battery Health: pandas sudah membaca "N/A" sebagai NaN.
        df['battery_health_raw'] = pd.to_numeric(df['Battery Health'], errors='coerce')

        # --- Imputasi Battery Health ---
        df['bh_imputed'] = df['battery_health_raw'].isna()

        median_per_varian = df.groupby(['Kategori Varian', 'penyimpanan_norm'])[
            'battery_health_raw'
        ].transform('median')
        median_per_seri = df.groupby('Kategori Seri')['battery_health_raw'].transform('median')
        median_global = df['battery_health_raw'].median()

        df['battery_health_final'] = df['battery_health_raw']
        df['battery_health_final'] = df['battery_health_final'].fillna(median_per_varian)
        df['battery_health_final'] = df['battery_health_final'].fillna(median_per_seri)
        df['battery_health_final'] = df['battery_health_final'].fillna(median_global)

        # --- Trust score ---
        rating_norm = df['Rating Produk'] / 5.0
        log_terjual = df['Produk Terjual'].apply(lambda x: math.log(x + 1))
        log_terjual_norm = (log_terjual - log_terjual.min()) / (
            (log_terjual.max() - log_terjual.min()) or 1
        )
        trust_raw = 0.5 * rating_norm + 0.5 * log_terjual_norm
        trust_raw = trust_raw + df['has_rating'].apply(lambda x: 0.1 if x else 0.0)
        df['trust_score'] = trust_raw.clip(upper=1.0)

        # --- Dokumen teks untuk BM25 ---
        def build_dokumen(row):
            bh = round(row['battery_health_final']) if pd.notna(row['battery_health_final']) else 'unknown'
            text = (
                f"{row['Kategori Varian']} {row['penyimpanan_norm']} {row['kondisi']} "
                f"battery health {bh} {row['Platform']} {row['Wilayah Toko']}"
            )
            tokens = [t for t in text.lower().split() if t not in STOPWORDS_ID]
            return ' '.join(tokens)

        df['dokumen_teks'] = df.apply(build_dokumen, axis=1)

        # --- Bulk create ---
        IphoneListing.objects.all().delete()

        objects = [
            IphoneListing(
                platform=row['Platform'],
                nama_toko=row['Nama Toko'],
                rating_produk=row['Rating Produk'],
                has_rating=row['has_rating'],
                produk_terjual=row['Produk Terjual'],
                kategori_seri=row['Kategori Seri'],
                kategori_varian=row['Kategori Varian'],
                penyimpanan=row['penyimpanan_norm'],
                battery_health=row['battery_health_final'],
                bh_imputed=row['bh_imputed'],
                harga=row['harga_int'],
                wilayah_toko=row['Wilayah Toko'],
                link_pembelian=row['Link Pembelian'],
                kondisi=row['kondisi'],
                generasi=row['generasi'],
                is_pro=row['is_pro'],
                penyimpanan_gb=row['penyimpanan_gb'],
                varian_model=row['varian_model'],
                garansi=row['garansi'],
                dokumen_teks=row['dokumen_teks'],
                trust_score=row['trust_score'],
            )
            for _, row in df.iterrows()
        ]

        IphoneListing.objects.bulk_create(objects)

        self.stdout.write(
            self.style.SUCCESS(f'Berhasil import {len(objects)} listing ke database.')
        )
