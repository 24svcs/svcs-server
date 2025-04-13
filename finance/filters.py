from django_filters.rest_framework import FilterSet
from .models import Client, Invoice, Payment


class ClientFilter(FilterSet):
    class Meta:
        model = Client
        fields = {
            'status': ['exact'],
        }
        


class InvoiceFilter(FilterSet):
    class Meta:
        model = Invoice
        fields = {
            'status': ['exact'],
            'due_date': ['gte', 'lte'],
            'issue_date': ['gte', 'lte'],
        }


class PaymentFilter(FilterSet):
    class Meta:
        model = Payment
        fields = {
            'status': ['exact'],
            'payment_date': ['gte', 'lte'],
        }
