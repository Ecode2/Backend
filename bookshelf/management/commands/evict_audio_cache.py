"""Evict least-recently-accessed synthesized audio past a size budget."""

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Sum

from bookshelf.models import AudioSegmentCache
from bookshelf.storage_backends import get_audio_storage


class Command(BaseCommand):
    help = "Evict least-recently-accessed TTS audio cache entries past the budget."

    def add_arguments(self, parser):
        parser.add_argument(
            "--budget-bytes", type=int,
            default=getattr(settings, "AUDIO_CACHE_MAX_BYTES", 2 * 1024**3),
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        budget = options["budget_bytes"]
        dry_run = options["dry_run"]

        total = AudioSegmentCache.objects.aggregate(s=Sum("byte_size"))["s"] or 0
        self.stdout.write(f"Current audio cache size: {total / 1024**2:.1f} MiB")
        if total <= budget:
            self.stdout.write(self.style.SUCCESS("Under budget; nothing to evict."))
            return

        storage = get_audio_storage()
        freed = 0
        to_free = total - budget
        # Oldest access first.
        for entry in AudioSegmentCache.objects.order_by("last_accessed_at").iterator():
            if freed >= to_free:
                break
            self.stdout.write(f"evict {entry.cache_key[:12]} ({entry.byte_size} B)")
            if not dry_run:
                try:
                    if entry.storage_path:
                        storage.delete(entry.storage_path)
                except Exception:
                    self.stderr.write(f"  failed deleting {entry.storage_path}")
                entry.delete()
            freed += entry.byte_size

        msg = f"Freed ~{freed / 1024**2:.1f} MiB"
        self.stdout.write(self.style.SUCCESS(msg + (" (dry run)" if dry_run else "")))
