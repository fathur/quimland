from django.db import models

from .base import TimestampMixin


class Setting(TimestampMixin):
    key   = models.CharField(max_length=100, primary_key=True)
    value = models.TextField()

    class Meta:
        db_table = 'settings'

    def __str__(self):
        return f'{self.key} = {self.value}'
