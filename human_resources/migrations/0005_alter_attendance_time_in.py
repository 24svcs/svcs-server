# Generated by Django 5.1.7 on 2025-03-28 22:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('human_resources', '0004_attendance_overtime_hours'),
    ]

    operations = [
        migrations.AlterField(
            model_name='attendance',
            name='time_in',
            field=models.TimeField(blank=True, null=True),
        ),
    ]
