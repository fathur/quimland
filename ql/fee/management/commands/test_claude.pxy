import base64
import json
import os

from django.core.management.base import BaseCommand

from anthropic import Anthropic


class Command(BaseCommand):
    help = "Test Claude image extraction."

    def add_arguments(self, parser):
        parser.add_argument("image_path", type=str, help="Path to the image file")

    def handle(self, *args, **options):
        image_path = options["image_path"]

        with open(image_path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")

        # Detect media type from extension
        ext = os.path.splitext(image_path)[1].lower()
        media_type_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        media_type = media_type_map.get(ext, "image/jpeg")

        client = Anthropic(api_key=os.environ["CLAUDE_API_KEY"])

        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": (
                        "You are a receipt data extraction assistant. Your job is to analyze bank transfer receipt images "
                        "and extract structured information from them accurately.\n\n"
                        "Given a receipt image, extract the following fields:\n"
                        "- bank_name: The name of the sending bank (e.g. BCA, BNI, BRI, Mandiri, CIMB, Jenius, GoPay, OVO, Dana, etc.)\n"
                        "- sender: The full name of the person or account sending the money\n"
                        "- receiver: The full name of the person or account receiving the money\n"
                        "- nominal: The transfer amount as a decimal number without currency symbols or separators (e.g. 150000.00)\n"
                        "- sent_at: The date and time the transfer was made, formatted as `yyyy-MM-dd HH:mm:ss`\n\n"
                        "Rules:\n"
                        "- Return ONLY a valid JSON object. Do not wrap it in markdown, backticks, or code fences. Output the raw JSON directly.\n"
                        "- If a field cannot be determined from the image, use null for that field.\n"
                        "- For nominal, always use decimal format with two decimal places (e.g. 100000.00, not Rp100.000).\n"
                        "- For sent_at, convert to 24-hour time if the receipt shows 12-hour format.\n"
                        "- For bank_name, use the common short name (e.g. 'BCA' not 'PT Bank Central Asia Tbk').\n"
                        "- For sender and receiver, use the name as shown on the receipt without account numbers.\n\n"
                        "Examples of correct output:\n\n"
                        "Example 1 — BCA transfer:\n"
                        '{"bank_name": "BCA", "sender": "Budi Santoso", "receiver": "Paguyuban Quim Land", "nominal": 500000.00, "sent_at": "2026-06-15 09:30:00"}\n\n'
                        "Example 2 — BNI transfer:\n"
                        '{"bank_name": "BNI", "sender": "Siti Rahayu", "receiver": "Yayasan Makmur Jaya", "nominal": 1500000.00, "sent_at": "2026-06-20 14:05:22"}\n\n'
                        "Example 3 — GoPay transfer:\n"
                        '{"bank_name": "GoPay", "sender": "Ahmad Fauzi", "receiver": "Toko Berkah Abadi", "nominal": 75000.00, "sent_at": "2026-07-01 11:45:10"}\n\n'
                        "Example 4 — Mandiri transfer with null field:\n"
                        '{"bank_name": "Mandiri", "sender": "Dewi Lestari", "receiver": null, "nominal": 250000.00, "sent_at": "2026-07-03 08:00:00"}\n\n'
                        "Now analyze the provided receipt image and return the JSON object.\n\n"
                        "CRITICAL: Your entire response must be a single raw JSON object. "
                        "Do not use markdown. Do not use backticks. Do not write ```json or ``` anywhere. "
                        "Do not add any text before or after the JSON. Start your response with { and end with }."
                    ),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                    ],
                },
                {
                    "role": "assistant",
                    "content": "{",
                },
            ],
        )

        result = json.loads("{" + response.content[0].text)
        # self.stdout.write(self.style.SUCCESS(str(result)))
        self.stdout.write(result["bank_name"])

        usage = response.usage
        self.stdout.write(
            f"\n[cache] created={usage.cache_creation_input_tokens} "
            f"read={usage.cache_read_input_tokens} "
            f"input={usage.input_tokens}"
        )
