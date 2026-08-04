from django.apps import AppConfig


class FeeConfig(AppConfig):
    name = 'ql.fee'
    label = 'fee'

    def ready(self):
        from pillow_heif import register_heif_opener
        register_heif_opener()
