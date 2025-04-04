
from rest_framework.viewsets import ModelViewSet, GenericViewSet
from .serializers import Client, ClientSerializer, CreateClientSerializer
from rest_framework.permissions import IsAuthenticated
from api.pagination import DefaultPagination
from django_filters.rest_framework import DjangoFilterBackend
from .filters import ClientFilter
from django.db import models
from rest_framework.response import Response

class ClientModelViewset(ModelViewSet):
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = ClientFilter
    search_fields = ['name__istartswith', 'email__istartswith', 'phone__exact', 'company_name__istartswith', 'tax_number__istartswith']
    ordering_fields = ['name', 'email', 'phone', 'company_name', 'tax_number']

    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Client.objects.select_related('address').prefetch_related('invoices', 'payments').filter(organization_id=self.kwargs['organization_pk'])
    
    serializer_class = ClientSerializer
    
    def get_serializer_class(self):
        if self.request.method in ['POST', 'PUT', 'PATCH']:
            return CreateClientSerializer
        return super().get_serializer_class()
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['organization_id'] = self.kwargs['organization_pk']
        return context

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            
            # Get current date for new clients calculation
            from django.utils import timezone
            from datetime import timedelta
            current_date = timezone.now()
            thirty_days_ago = current_date - timedelta(days=30)
            
            # Calculate statistics
            stats = Client.objects.filter(organization_id=self.kwargs['organization_pk']).aggregate(
                total_clients=models.Count('id'),
                active_clients=models.Count('id', filter=models.Q(is_active=True)),
                inactive_clients=models.Count('id', filter=models.Q(is_active=False)),
                new_clients_30d=models.Count('id', filter=models.Q(created_at__gte=thirty_days_ago)),
                clients_with_outstanding_balance=models.Count(
                    'id',
                    filter=models.Q(invoices__status='UNPAID') | models.Q(invoices__status='OVERDUE'),
                    distinct=True
                )
            )
            
            response.data['statistics'] = stats
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    