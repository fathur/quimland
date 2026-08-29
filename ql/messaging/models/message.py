from django.conf import settings
from django.db import models

from ql.common.base import TimestampMixin


class Message(TimestampMixin):
    id = models.BigAutoField(primary_key=True)

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='received_messages',
    )
    content = models.TextField()
