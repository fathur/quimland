from django.core.management.base import BaseCommand, CommandError

from ql.fee.services.whatsapp_client import WhatsAppAPIError, send_template_message, send_text_message


class Command(BaseCommand):
    help = 'Send a WhatsApp message via the Meta Cloud API (plain text or an approved template).'

    def add_arguments(self, parser):
        parser.add_argument('to', help='Recipient phone number, e.g. 628123456789 (no leading +)')
        parser.add_argument('message', nargs='?', default=None, help='Text message body (omit when using --template)')
        parser.add_argument('--template', help='Name of an approved template to send instead of free text')
        parser.add_argument('--lang', default='en_US', help='Template language code (default: en_US)')
        parser.add_argument(
            '--param', action='append', default=[],
            help='Template body parameter, in order (repeatable: --param a --param b)',
        )
        parser.add_argument(
            '--header-param', action='append', default=[],
            help='Template header parameter, in order (repeatable)',
        )

    def handle(self, *args, **options):
        try:
            if options['template']:
                result = send_template_message(
                    options['to'], options['template'], options['lang'],
                    options['param'], options['header_param'],
                )
            else:
                if not options['message']:
                    raise CommandError('message is required unless --template is given')
                result = send_text_message(options['to'], options['message'])
        except WhatsAppAPIError as exc:
            raise CommandError(str(exc))

        message_id = result['messages'][0]['id']
        self.stdout.write(self.style.SUCCESS(f'Sent. message id: {message_id}'))
