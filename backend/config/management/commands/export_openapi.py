"""Export the OpenAPI schema from the Ninja API (for frontend TS codegen)."""
import json

from django.core.management.base import BaseCommand
from ninja.openapi.schema import get_schema

from config.api import api


class Command(BaseCommand):
    help = "Write openapi.json (OpenAPI 3) for the frontend TypeScript codegen."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="openapi.json", help="Destination path")

    def handle(self, *args, **options):
        schema = get_schema(api, path_prefix="/api/")  # ninja: a dict subclass
        with open(options["output"], "w", encoding="utf-8") as out:
            json.dump(dict(schema), out, indent=2, default=str)
        self.stdout.write(
            self.style.SUCCESS(f'Wrote {options["output"]} ({len(schema.get("paths", {}))} paths)')
        )
