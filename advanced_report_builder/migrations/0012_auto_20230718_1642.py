# Generated by Django 3.2.7 on 2023-07-18 16:42

from django.db import migrations
import django_modals.model_fields.colour


class Migration(migrations.Migration):

    dependencies = [
        ('advanced_report_builder', '0011_auto_20230620_1449'),
    ]

    operations = [
        migrations.AlterField(
            model_name='singlevaluereport',
            name='tile_colour',
            field=django_modals.model_fields.colour.ColourField(blank=True, max_length=10, null=True),
        ),
        migrations.AlterField(
            model_name='target',
            name='colour',
            field=django_modals.model_fields.colour.ColourField(blank=True, help_text='The colour when it gets displayed on a report', max_length=10, null=True),
        ),
    ]
