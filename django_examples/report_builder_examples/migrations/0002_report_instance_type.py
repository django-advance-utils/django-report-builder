# Generated by Django 3.2.7 on 2021-10-05 13:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('report_builder_examples', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='report',
            name='instance_type',
            field=models.CharField(default=' ', max_length=255),
            preserve_default=False,
        ),
    ]
