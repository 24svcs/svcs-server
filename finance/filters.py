from django_filters.rest_framework import FilterSet
from .models import Client


class ClientFilter(FilterSet):
    class Meta:
        model = Client
        fields = {
            'is_active': ['exact'],
        }