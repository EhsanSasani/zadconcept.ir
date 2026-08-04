import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


MODULE_IMPORT_RE = re.compile(
    r"(?:\bfrom\s*|\bimport\s*(?:\(\s*)?)[\"'](?P<path>\.{1,2}/[^\"']+\.js)[\"']"
)
HASHED_MODULE_RE = re.compile(r"\.[0-9a-f]{12}\.js$")


def audit_module_manifest(static_root, source_root=None):
    static_root = Path(static_root)
    manifest_path = static_root / "staticfiles.json"
    if not manifest_path.exists():
        return [f"Static manifest is missing: {manifest_path}"]

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Static manifest is unreadable: {exc}"]

    errors = []
    paths = manifest.get("paths", {})
    source_root = Path(
        source_root or Path(settings.BASE_DIR, "main", "static", "main", "js")
    )
    module_sources = source_root.rglob("*.js")

    for source_path in module_sources:
        source = source_path.read_text(encoding="utf-8")
        if not MODULE_IMPORT_RE.search(source):
            continue

        source_name = f"main/js/{source_path.relative_to(source_root).as_posix()}"
        collected_name = paths.get(source_name)
        if not collected_name:
            errors.append(f"Module is absent from manifest: {source_name}")
            continue

        collected_path = static_root / collected_name
        if not collected_path.exists():
            errors.append(f"Collected module is missing: {collected_name}")
            continue

        collected_source = collected_path.read_text(encoding="utf-8")
        for match in MODULE_IMPORT_RE.finditer(collected_source):
            imported_path = match.group("path")
            if not HASHED_MODULE_RE.search(imported_path):
                errors.append(
                    f"Unversioned import in {collected_name}: {imported_path}"
                )

    return errors


class Command(BaseCommand):
    help = "Verify that collectstatic rewrote native ES-module imports to hashed paths."

    def handle(self, *args, **options):
        errors = audit_module_manifest(settings.STATIC_ROOT)
        if errors:
            raise CommandError("\n".join(errors))
        self.stdout.write(self.style.SUCCESS("Static module manifest audit passed."))
