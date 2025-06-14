# Generated by Django 5.1.7 on 2025-04-02 18:00

import django.db.models.deletion
import organization.models
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organization', '0002_delete_memberinvitation'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Invitation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email', models.EmailField(max_length=254)),
                ('name', models.CharField(max_length=255)),
                ('message', models.TextField(blank=True, null=True)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('ACCEPTED', 'Accepted'), ('REJECTED', 'Rejected'), ('CREATED', 'Created')], default='PENDING', max_length=10)),
                ('invited_at', models.DateTimeField(auto_now_add=True)),
                ('is_updated', models.BooleanField(default=False, editable=False)),
                ('expires_at', models.DateTimeField(default=organization.models.default_expiration)),
                ('invited_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invitations', to='organization.organization')),
            ],
            options={
                'verbose_name_plural': 'Invitations',
                'indexes': [models.Index(fields=['organization'], name='organizatio_organiz_18fb49_idx'), models.Index(fields=['email'], name='organizatio_email_149813_idx'), models.Index(fields=['status'], name='organizatio_status_f689fd_idx')],
                'constraints': [models.UniqueConstraint(condition=models.Q(('status', 'PENDING')), fields=('organization', 'email'), name='unique_pending_invitation_per_email'), models.UniqueConstraint(condition=models.Q(('status', 'ACCEPTED')), fields=('organization', 'email'), name='unique_accepted_invitation_per_email')],
            },
        ),
    ]
