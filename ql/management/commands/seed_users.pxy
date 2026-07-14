import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from ql.models import UserProperty, Tariff

USERS = [
    ('Wahyu Candra Mardianto',  'A1',  'OCCUPIED'),
    ('Rochmad Santosa',         'A2',  'OCCUPIED'),
    ('Dian Jaelani',            'A3',  'OCCUPIED'),
    ('Imade Tias W.',           'A4',  'RENT'),
    ('Fathur Rohman',           'A5',  'OCCUPIED'),
    ('Kusdianto',               'A6',  'OCCUPIED'),
    ('Dewangga Alviano R.',     'A7',  'OCCUPIED'),
    ('Bayu Triwidiantara',      'A8',  'OCCUPIED'),
    ('Abdul Muchlis',           'B2',  'OCCUPIED'),
    ('Pupus Wasesa',            'B3',  'OCCUPIED'),
    ('Fanharil Ardian',         'B4',  'OCCUPIED'),
    ('Agus',                    'B5',  'VACANT'),
    ('Lina',                    'B6',  'VACANT'),
    ('Candra / Susan',          'B7',  'OCCUPIED'),
    ('Heri Murjito',            'B8',  'OCCUPIED'),
    ('Jon Pardede',             'C1',  'OCCUPIED'),
    ('Reza Wahyu Prasetyo',     'C2',  'OCCUPIED'),
    ('Gery Prizlanto',          'C3',  'OCCUPIED'),
    ('Dhedy Wismandalu',        'C4',  'OCCUPIED'),
    ('Rendy',                   'C5',  'OCCUPIED'),
    ('Ikhwan MP',               'C6',  'OCCUPIED'),
    ('Bagas',                   'C7',  'OCCUPIED'),
    ('Taufiq',                  'C8',  'OCCUPIED'),
    ('Rangga Jayadi',           'D1',  'OCCUPIED'),
    ('Ruji Martono',            'D2',  'OCCUPIED'),
    ('Untung',                  'D3',  'OCCUPIED'),
    ('Arga Mahardika',          'D4',  'OCCUPIED'),
    ('Ryan Rifai',              'E1',  'OCCUPIED'),
    ('Awang Budiharja',         'E2',  'OCCUPIED'),
    ('Khoirul Parto',           'E3',  'OCCUPIED'),
    ('Kristiawan Nur',          'F2',  'OCCUPIED'),
    ('Afif Riandika',           'F3',  'VACANT'),
    ('Tegar Iman Taufiq',       'F4',  'OCCUPIED'),
    ('Willy Wihardja',          'G1',  'OCCUPIED'),
    ('Riza El Fahruddin',       'G2',  'OCCUPIED'),
    ('Haris Ari Mukti',         'G3',  'OCCUPIED'),
    ('Batu',                    'G4',  'RENT'),
    ('Burhan',                  'G5',  'OCCUPIED'),
    ('Hengky Setyo Nugroho',    'G6',  'OCCUPIED'),
    ('Galang',                  'G7',  'OCCUPIED'),
    ('Budi C Hutomo',           'G8',  'OCCUPIED'),
    ('Almas Almasih',           'G9',  'OCCUPIED'),
    ('Abid Fatchul Amin',       'G10', 'OCCUPIED'),
    ('Giri Putra',              'G11', 'OCCUPIED'),
    ('Niko Haryanto',           'G12', 'OCCUPIED'),
    ('Yohanes Bayu Adistara',   'H1',  'OCCUPIED'),
    ('Khalid Umar',             'H4',  'OCCUPIED'),
    ('Awang Bayu Aji',          'H5',  'OCCUPIED'),
    ('Afil Riandika',           'H10', 'VACANT'),
    ('Setiyawan Prayogo',       'H16', 'VACANT'),
    ('Lukas Fajar Aditya',      'H18', 'OCCUPIED'),
    ('Bagus Sigit Pambudi',     'H20', 'OCCUPIED'),
    ('Muhammad Saiful Huda',    'H24', 'OCCUPIED'),
    ('Herlambang Setyo Aji',    'H25', 'RENT'),
    ('Darmadi',                 'H26', 'OCCUPIED'),
    ('Risa Bagus Andriyono',    'H27', 'OCCUPIED'),
    ('Habib Trizaka',           'H30', 'OCCUPIED'),
]


def _make_username(full_name):
    slug = re.sub(r'\s+', '_', full_name.lower())
    return re.sub(r'[^a-z0-9_]', '', slug)


class Command(BaseCommand):
    help = 'Seed all RT residents into the database.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            default=True,
            help='Skip users whose username already exists (default: on)',
        )

    def handle(self, *args, **options):
        User = get_user_model()
        created = skipped = 0

        for full_name, home_number, status in USERS:
            username = _make_username(full_name)
            if User.objects.filter(username=username).exists():
                user = User.objects.get(username=username)
            else:
                parts = full_name.split(None, 1)
                user = User.objects.create_user(
                    username=username,
                    password=None,
                    first_name=parts[0],
                    last_name=parts[1] if len(parts) > 1 else '',
                )

            if not UserProperty.objects.filter(user=user).exists():
                UserProperty.objects.create(
                    user=user,
                    occupancy_status=status,
                    home_number=home_number,
                )

            if not Tariff.objects.filter(user=user, kind=Tariff.Kind.MONTHLY).exists():
                Tariff.objects.create(
                    user=user,
                    kind=Tariff.Kind.MONTHLY,
                    nominal=70_000,
                    start_from='2026-01-01',
                )

            if not Tariff.objects.filter(user=user, kind=Tariff.Kind.GARBAGE).exists():
                Tariff.objects.create(
                    user=user,
                    kind=Tariff.Kind.GARBAGE,
                    nominal=30_000,
                    start_from='2026-01-01',
                )

            self.stdout.write(f'  add   {username} ({home_number}, {status})')
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nDone — {created} created, {skipped} skipped.'
        ))
