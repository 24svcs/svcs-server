from django_filters.rest_framework import FilterSet
from .models import Client, Invoice


class ClientFilter(FilterSet):
    class Meta:
        model = Client
        fields = {
            'is_active': ['exact'],
        }
        


class InvoiceFilter(FilterSet):
    class Meta:
        model = Invoice
        fields = {
            'status': ['exact'],
            'due_date': ['gte', 'lte'],
            'issue_date': ['gte', 'lte'],
        }
