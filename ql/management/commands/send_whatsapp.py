from django.core.management.base import BaseCommand, CommandError

from ql.services.whatsapp_client import WhatsAppAPIError, send_text_message


class Command(BaseCommand):
    help = 'Send a test WhatsApp text message via the Meta Cloud API.'

    def add_arguments(self, parser):
        parser.add_argument('to', help='Recipient phone number, e.g. 628123456789 (no leading +)')
        parser.add_argument('message', help='Text message body')

    def handle(self, *args, **options):
        try:
            result = send_text_message(options['to'], options['message'])
        except WhatsAppAPIError as exc:
            raise CommandError(str(exc))

        message_id = result['messages'][0]['id']
        self.stdout.write(self.style.SUCCESS(f'Sent. message id: {message_id}'))
