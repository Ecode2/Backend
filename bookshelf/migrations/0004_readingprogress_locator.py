from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookshelf", "0003_alter_bookfile_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="readingprogress",
            name="locator",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
