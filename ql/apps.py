from django.apps import AppConfig


class QlConfig(AppConfig):
    name = 'ql'

    def ready(self):
        from pillow_heif import register_heif_opener
        register_heif_opener()
