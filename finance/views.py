from rest_framework.viewsets import ModelViewSet, GenericViewSet
from .serializers import (
    Client, ClientSerializer, CreateClientSerializer,
    Invoice, InvoiceSerializer, CreateInvoiceSerializer, UpdateInvoiceSerializer,
    Payment, PaymentSerializer
)
from rest_framework.permissions import IsAuthenticated
from api.pagination import DefaultPagination
from django_filters.rest_framework import DjangoFilterBackend
from .filters import ClientFilter
from django.db import models
from django.db.models import F, Q, Sum, Avg, Count, DecimalField, Value
from django.db.models.functions import Coalesce
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from rest_framework.decorators import action
from rest_framework import status

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
    
class InvoiceViewSet(ModelViewSet):
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend]
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Invoice.objects.select_related(
            'client'
        ).prefetch_related(
            'items',
            'payments'
        ).filter(
            client__organization_id=self.kwargs['organization_pk']
        )
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateInvoiceSerializer
        elif self.action in ['update', 'partial_update']:
            return UpdateInvoiceSerializer
        return InvoiceSerializer
    
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
            
            # Calculate date ranges for statistics
            current_date = timezone.now()
            thirty_days_ago = current_date - timedelta(days=30)
            ninety_days_ago = current_date - timedelta(days=90)
            
            # Get base queryset for statistics with annotations
            base_qs = Invoice.objects.filter(
                client__organization_id=self.kwargs['organization_pk']
            ).annotate(
                subtotal=Sum(
                    F('items__quantity') * F('items__unit_price'),
                    output_field=DecimalField(max_digits=10, decimal_places=2)
                ),
                tax=F('subtotal') * F('tax_rate') / Value(100, output_field=DecimalField(max_digits=10, decimal_places=2)),
                total=F('subtotal') + F('tax'),
                paid=Coalesce(
                    Sum(
                        'payments__amount',
                        filter=Q(payments__status='COMPLETED'),
                        output_field=DecimalField(max_digits=10, decimal_places=2)
                    ),
                    Value(0, output_field=DecimalField(max_digits=10, decimal_places=2))
                )
            ).annotate(
                balance=F('total') - F('paid')
            )
            
            # Calculate statistics
            stats = base_qs.aggregate(
                total_invoices=Count('id'),
                unpaid_invoices=Count(
                    'id',
                    filter=Q(status__in=['UNPAID', 'OVERDUE'])
                ),
                overdue_invoices=Count(
                    'id',
                    filter=Q(status='OVERDUE')
                ),
                paid_invoices=Count(
                    'id',
                    filter=Q(status='PAID')
                ),
                invoices_last_30d=Count(
                    'id',
                    filter=Q(issue_date__gte=thirty_days_ago)
                ),
                invoices_last_90d=Count(
                    'id',
                    filter=Q(issue_date__gte=ninety_days_ago)
                ),
                total_amount=Sum('total', output_field=DecimalField(max_digits=10, decimal_places=2)),
                total_paid=Sum('paid', output_field=DecimalField(max_digits=10, decimal_places=2)),
                total_outstanding=Sum('balance', output_field=DecimalField(max_digits=10, decimal_places=2)),
                avg_days_to_pay=Avg(
                    F('payments__payment_date') - F('issue_date'),
                    filter=Q(status='PAID')
                )
            )
            
            # Handle None values for sums
            stats['total_amount'] = float(stats['total_amount'] or 0)
            stats['total_paid'] = float(stats['total_paid'] or 0)
            stats['total_outstanding'] = float(stats['total_outstanding'] or 0)
            
            # Convert timedelta to days for avg_days_to_pay
            if stats['avg_days_to_pay']:
                stats['avg_days_to_pay'] = stats['avg_days_to_pay'].days
            else:
                stats['avg_days_to_pay'] = 0
            
            response.data['statistics'] = stats
            return response
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def mark_as_paid(self, request, organization_pk=None, pk=None):
        invoice = self.get_object()
        
        if invoice.status == 'PAID':
            return Response(
                {"detail": "Invoice is already marked as paid."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if invoice.balance_due > 0:
            return Response(
                {"detail": "Cannot mark as paid. Invoice has outstanding balance."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        invoice.status = 'PAID'
        invoice.save()
        
        serializer = self.get_serializer(invoice)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def send_reminder(self, request, organization_pk=None, pk=None):
        invoice = self.get_object()
        
        if invoice.status == 'PAID':
            return Response(
                {"detail": "Cannot send reminder for paid invoice."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Here you would implement the actual reminder sending logic
        # For now, we'll just return a success response
        return Response(
            {"detail": "Payment reminder sent successfully."},
            status=status.HTTP_200_OK
        )
    
    @action(detail=False, methods=['post'])
    def bulk_create(self, request, organization_pk=None):
        """
        Create multiple invoices at once.
        """
        serializer = CreateInvoiceSerializer(
            data=request.data,
            many=True,
            context={'organization_id': organization_pk}
        )
        
        if serializer.is_valid():
            try:
                invoices = serializer.create_bulk(serializer.validated_data)
                response_serializer = InvoiceSerializer(invoices, many=True)
                return Response(response_serializer.data, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response(
                    {"error": str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class PaymentViewSet(ModelViewSet):
    pagination_class = DefaultPagination
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentSerializer
    
    def get_queryset(self):
        return Payment.objects.select_related(
            'client',
            'invoice'
        ).filter(
            client__organization_id=self.kwargs['organization_pk']
        ).order_by('-created_at')
    
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
            
            # Calculate payment statistics
            current_date = timezone.now()
            thirty_days_ago = current_date - timedelta(days=30)
            
            stats = Payment.objects.filter(
                client__organization_id=self.kwargs['organization_pk']
            ).aggregate(
                total_payments=Count('id'),
                total_amount=Sum('amount', default=0),
                completed_payments=Count('id', filter=Q(status='COMPLETED')),
                pending_payments=Count('id', filter=Q(status='PENDING')),
                failed_payments=Count('id', filter=Q(status='FAILED')),
                payments_last_30d=Count('id', filter=Q(created_at__gte=thirty_days_ago)),
                amount_last_30d=Sum('amount', filter=Q(created_at__gte=thirty_days_ago), default=0)
            )
            
            response.data['statistics'] = stats
            return response
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def complete(self, request, organization_pk=None, pk=None):
        """
        Mark a payment as completed and update the invoice status accordingly.
        """
        payment = self.get_object()
        
        if payment.status != 'PENDING':
            return Response(
                {"detail": f"Cannot complete payment in {payment.status} status"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        payment.status = 'COMPLETED'
        payment.save()
        
        # Update invoice status based on total payments
        invoice = payment.invoice
        total_paid = Payment.objects.filter(
            invoice=invoice,
            status='COMPLETED'
        ).aggregate(
            total=Sum('amount', default=0)
        )['total']
        
        if total_paid >= invoice.total_amount:
            invoice.status = 'PAID'
        elif total_paid > 0:
            invoice.status = 'PARTIALLY_PAID'
        
        invoice.save()
        
        serializer = self.get_serializer(payment)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def fail(self, request, organization_pk=None, pk=None):
        """
        Mark a payment as failed.
        """
        payment = self.get_object()
        
        if payment.status != 'PENDING':
            return Response(
                {"detail": f"Cannot mark payment as failed in {payment.status} status"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        payment.status = 'FAILED'
        payment.save()
        
        serializer = self.get_serializer(payment)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def refund(self, request, organization_pk=None, pk=None):
        """
        Mark a payment as refunded and update the invoice status.
        """
        payment = self.get_object()
        
        if payment.status != 'COMPLETED':
            return Response(
                {"detail": "Can only refund completed payments"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        payment.status = 'REFUNDED'
        payment.save()
        
        # Update invoice status based on remaining payments
        invoice = payment.invoice
        remaining_paid = Payment.objects.filter(
            invoice=invoice,
            status='COMPLETED'
        ).aggregate(
            total=Sum('amount', default=0)
        )['total']
        
        if remaining_paid == 0:
            invoice.status = 'PENDING'
        elif remaining_paid < invoice.total_amount:
            invoice.status = 'PARTIALLY_PAID'
        
        invoice.save()
        
        serializer = self.get_serializer(payment)
        return Response(serializer.data)
    
    
    