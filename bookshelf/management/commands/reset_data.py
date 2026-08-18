"""Wipe all Bookverse data: database rows AND the object-storage bucket.

Destructive and irreversible, so it refuses to run without --yes.

    python manage.py reset_data --yes            # rows + stored files
    python manage.py reset_data --yes --keep-users
    python manage.py reset_data --yes --db-only
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Delete all books, files, progress and stored objects."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true",
                            help="Required. Confirms the data loss.")
        parser.add_argument("--keep-users", action="store_true",
                            help="Keep auth users (only wipe bookshelf data).")
        parser.add_argument("--db-only", action="store_true",
                            help="Skip clearing the storage bucket.")
        parser.add_argument("--storage-only", action="store_true",
                            help="Only clear the bucket; touch no database rows. "
                                 "Use when the schema is being recreated anyway.")

    def handle(self, *args, **opts):
        if not opts["yes"]:
            raise CommandError("Refusing to wipe data without --yes.")

        if opts["storage_only"]:
            self._clear_bucket()
            self.stdout.write(self.style.SUCCESS("Storage cleared."))
            return

        from django.contrib.auth import get_user_model
        from bookshelf.models import (
            AudioChapter, AudioSegmentCache, Book, BookFile, Bookmark,
            DocumentStructure, ReaderSettings, ReadingProgress,
        )

        # Children first so cascades never surprise us.
        models = [
            AudioChapter, DocumentStructure, BookFile, Bookmark,
            ReadingProgress, AudioSegmentCache, ReaderSettings, Book,
        ]
        with transaction.atomic():
            for model in models:
                n, _ = model.objects.all().delete()
                self.stdout.write(f"  {model.__name__:20} deleted {n}")
            if not opts["keep_users"]:
                User = get_user_model()
                n, _ = User.objects.filter(is_superuser=False).delete()
                self.stdout.write(f"  {'User (non-superuser)':20} deleted {n}")

        if not opts["db_only"]:
            self._clear_bucket()

        self.stdout.write(self.style.SUCCESS("Reset complete."))

    def _clear_bucket(self):
        """Delete every object in the media bucket (S3/MinIO), else local media."""
        from django.conf import settings

        if not getattr(settings, "USE_S3", False):
            import shutil
            from pathlib import Path

            root = Path(getattr(settings, "MEDIA_ROOT", "")) if getattr(settings, "MEDIA_ROOT", "") else None
            if root and root.exists():
                for child in root.iterdir():
                    shutil.rmtree(child) if child.is_dir() else child.unlink()
                self.stdout.write(f"  cleared local media at {root}")
            return

        import boto3

        s3 = boto3.resource(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=getattr(settings, "AWS_S3_REGION_NAME", None),
            use_ssl=getattr(settings, "AWS_S3_USE_SSL", True),
        )
        bucket = s3.Bucket(settings.AWS_STORAGE_BUCKET_NAME)
        count = 0
        # delete_objects caps at 1000 keys per call.
        batch = []
        for obj in bucket.objects.all():
            batch.append({"Key": obj.key})
            if len(batch) == 1000:
                bucket.delete_objects(Delete={"Objects": batch})
                count += len(batch)
                batch = []
        if batch:
            bucket.delete_objects(Delete={"Objects": batch})
            count += len(batch)
        self.stdout.write(f"  cleared {count} objects from bucket "
                          f"'{settings.AWS_STORAGE_BUCKET_NAME}'")
