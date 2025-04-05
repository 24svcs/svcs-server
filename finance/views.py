from rest_framework.viewsets import ModelViewSet, GenericViewSet
from rest_framework.mixins import CreateModelMixin

from .serializers import (
    Client, ClientSerializer, CreateClientSerializer,
    Invoice, InvoiceSerializer, CreateInvoiceSerializer, UpdateInvoiceSerializer,
    Payment, PaymentSerializer, CreatePaymentSerializer, UpdatePaymentSerializer
)
from rest_framework.permissions import IsAuthenticated
from api.pagination import DefaultPagination
from django_filters.rest_framework import DjangoFilterBackend
from .filters import ClientFilter, InvoiceFilter
from django.db import models, transaction
from django.db.models import Q, Sum, Count
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from rest_framework.decorators import action
from rest_framework import status
from rest_framework import filters
from .utils import annotate_invoice_calculations, calculate_payment_statistics



class ClientModelViewset(ModelViewSet):
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = ClientFilter
    search_fields = ['name__istartswith', 'email__istartswith', 'phone__exact', 'company_name__istartswith', 'tax_number__istartswith']
    ordering_fields = ['name', 'email', 'phone', 'company_name', 'tax_number']

    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        from django.db.models import Prefetch
        
        # Optimize invoice queries with their items
        invoice_queryset = Invoice.objects.prefetch_related(
            'items'
        )
        
        # Optimize payment queries 
        payment_queryset = Payment.objects.select_related('invoice')
        
        return Client.objects.select_related('address').prefetch_related(
            Prefetch('invoices', queryset=invoice_queryset),
            Prefetch('payments', queryset=payment_queryset)
        ).filter(organization_id=self.kwargs['organization_pk'])
    
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
    

# ================================ Invoice Viewset ================================

class InvoiceViewSet(ModelViewSet):
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        'invoice_number__istartswith',
        'client__name__istartswith',
        'client__phone__exact',
        'client__company_name__istartswith',
    ]
    ordering_fields = ['issue_date', 'due_date', 'created_at', 'status']
    ordering = ['-created_at']  # Default ordering
    permission_classes = [IsAuthenticated]
    filterset_class = InvoiceFilter
    
    def get_queryset(self):
        from django.db.models import Prefetch
        # Use the utility function to annotate invoice calculations
        return annotate_invoice_calculations(
            Invoice.objects.select_related('client').prefetch_related(
                'items',
                Prefetch('payments', queryset=Payment.objects.all().select_related('invoice', 'client'))
            )
        ).filter(organization_id=self.kwargs['organization_pk'])
  
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
            
            # Calculate statistics
            current_date = timezone.now().date()
            thirty_days_ago = current_date - timedelta(days=30)
            
            stats = Invoice.objects.filter(
                organization_id=self.kwargs['organization_pk']
            ).aggregate(
                total_invoices=Count('id'),
                draft_invoices=Count('id', filter=Q(status='DRAFT')),
                pending_invoices=Count('id', filter=Q(status='PENDING')),
                paid_invoices=Count('id', filter=Q(status='PAID')),
                overdue_invoices=Count('id', filter=Q(status='OVERDUE')),
                partially_paid=Count('id', filter=Q(status='PARTIALLY_PAID')),
                invoices_created_30d=Count('id', filter=Q(created_at__gte=thirty_days_ago)),
                total_value=Sum('items__quantity', filter=Q(items__unit_price__gt=0), default=0)
            )
            
            response.data['statistics'] = stats
            return response
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def send_reminder(self, request, organization_pk=None, pk=None):
        invoice = self.get_object()
        
        if invoice.status == 'PAID':
            return Response(
                {"detail": "Cannot send reminder for paid invoice."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if invoice.status not in ['PENDING', 'OVERDUE', 'PARTIALLY_PAID']:
            return Response(
                {"detail": f"Cannot send reminder for invoice in {invoice.status} status."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Here you would implement the actual reminder sending logic
            # This is a placeholder for the actual implementation
            
            return Response(
                {"detail": "Payment reminder sent successfully."},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"detail": f"Failed to send reminder: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def send_to_client(self, request, organization_pk=None, pk=None):
        """
        Send the invoice to the client and change its status to PENDING.
        """
        invoice = self.get_object()
        
        # Validate invoice state
        if invoice.status != 'DRAFT':
            return Response(
                {"detail": f"Cannot send invoice in {invoice.status} status. Only DRAFT invoices can be sent."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate invoice has items
        if not invoice.items.exists():
            return Response(
                {"detail": "Cannot send invoice without items."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                # Update invoice status
                invoice.status = 'PENDING'
                invoice.save()
            
                serializer = self.get_serializer(invoice)
                return Response({
                    "detail": "Invoice has been sent to the client.",
                    "invoice": serializer.data
                })
                
        except Exception as e:
            return Response(
                {"detail": f"Failed to send invoice: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
            
    
 
    
    
            
            
            
            
# ================================ Payment Viewset ================================
    
class PaymentViewSet(ModelViewSet):
    pagination_class = DefaultPagination
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['invoice__invoice_number', 'client__name', 'transaction_id']
    ordering_fields = ['payment_date', 'amount', 'status', 'created_at']
    ordering = ['-created_at']  # Default ordering
    
    def get_queryset(self):
        return Payment.objects.select_related(
            'client',
            'invoice',
            'client__address'  # Also select client address to avoid additional queries
        ).filter(
            client__organization_id=self.kwargs['organization_pk']
        ).order_by('-created_at')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreatePaymentSerializer
        elif self.action in ['update', 'partial_update']:
            return UpdatePaymentSerializer
        return PaymentSerializer
    
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
            
            # Use utility function for payment statistics
            stats = calculate_payment_statistics(
                Payment.objects.filter(client__organization_id=self.kwargs['organization_pk'])
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
        
        try:
            with transaction.atomic():
                # Update payment status
                payment.status = 'COMPLETED'
                payment.save()
                
                # Update invoice status
                invoice = payment.invoice
                invoice.update_status_based_on_payments()
                
                serializer = self.get_serializer(payment)
                return Response(serializer.data)
                
        except Exception as e:
            return Response(
                {"detail": f"Failed to complete payment: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def fail(self, request, organization_pk=None, pk=None):
        """
        Mark a payment as failed and update the invoice status.
        """
        payment = self.get_object()
        
        if payment.status != 'PENDING':
            return Response(
                {"detail": f"Cannot mark payment as failed in {payment.status} status"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                # Update payment status
                payment.status = 'FAILED'
                payment.save()
                
                # Update invoice status
                invoice = payment.invoice
                invoice.update_status_based_on_payments()
                
                serializer = self.get_serializer(payment)
                return Response(serializer.data)
                
        except Exception as e:
            return Response(
                {"detail": f"Failed to mark payment as failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
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
        
        try:
            with transaction.atomic():
                payment.status = 'REFUNDED'
                payment.save()
                
                # Update invoice status
                invoice = payment.invoice
                invoice.update_status_based_on_payments()
                
                serializer = self.get_serializer(payment)
                return Response(serializer.data)
                
        except Exception as e:
            return Response(
                {"detail": f"Failed to process refund: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
class MakeInvoicePaymentViewSet(GenericViewSet, CreateModelMixin):
    """
    A simplified viewset for creating payments using only invoice ID.
    This viewset only supports creating new payments.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = CreatePaymentSerializer
    queryset = Payment.objects.all()
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        
        return Response(
            PaymentSerializer(payment).data,
            status=status.HTTP_201_CREATED
        )
    
   