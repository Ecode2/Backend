# Generated by Django 5.1 on 2025-01-11 23:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookshelf", "0002_book_total_page"),
    ]

    operations = [
        migrations.AlterField(
            model_name="book",
            name="total_page",
            field=models.IntegerField(blank=True, default=0, null=True),
        ),
    ]
