from django.conf import settings
from django.shortcuts import redirect
from rest_framework.viewsets import ModelViewSet, GenericViewSet
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin, UpdateModelMixin, ListModelMixin, RetrieveModelMixin
import logging
from decimal import Decimal, DecimalException, InvalidOperation

from core.services.currency import convert_currency
from finance.models import Expense
from finance.serializers.expense_serializers import CreateExpenseSerializer, ExpenseSerializer

from .serializer import (
    Invoice, InvoiceSerializer, CreateInvoiceSerializer, UpdateInvoiceSerializer,
    Payment, PaymentSerializer, CreatePaymentSerializer, UpdatePaymentSerializer,
    InvoiceItem, BulkInvoiceItemSerializer,
    RecurringInvoice, RecurringInvoiceSerializer, CreateRecurringInvoiceSerializer, UpdateRecurringInvoiceSerializer,

)
from rest_framework.permissions import IsAuthenticated
from api.pagination import DefaultPagination
from django_filters.rest_framework import DjangoFilterBackend
from .filters import ClientFilter, ExpenseFilter, InvoiceFilter, PaymentFilter
from django.db import models, transaction
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from rest_framework.decorators import action
from rest_framework import status
from rest_framework import filters
from .utils import annotate_invoice_calculations, calculate_payment_statistics
from api.throttling import BurstRateThrottle, SustainedRateThrottle
import uuid
from rest_framework.views import APIView
from django.http import HttpResponse
from rest_framework.permissions import AllowAny
from django.db.models import F, Prefetch, OuterRef, Subquery, ExpressionWrapper, DecimalField
from django.db.models.functions import Coalesce
from finance.serializers.client_serializers import  Client, ClientSerializer, CreateClientSerializer, UpdateClientSerializer, SimpleClientSerializer
from finance.serializers.address_serializers import (
    Address,
    AddressSerializer,
    CreateAddressSerializer,
    UpdateAddressSerializer
)
from finance.serializers.invoice_serializers import SimpleInvoiceSerializer
from core.services.moncash import MONCASH_MAX_AMOUNT, get_moncash_online_transaction_fee, process_moncash_payment, verify_moncash_payment, consume_moncash_payment
from django.template.loader import render_to_string
import datetime
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
logger = logging.getLogger(__name__)


class ClientModelViewset(ModelViewSet):
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = ClientFilter
    search_fields = ['name__istartswith', 'email__istartswith', 'phone__exact']
    ordering_fields = ['name']

    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # First, create a subquery to calculate invoice totals
      
        
        invoice_items_total = InvoiceItem.objects.filter(
            invoice=OuterRef('pk')
        ).values('invoice').annotate(
            items_total=Sum(F('quantity') * F('unit_price'))
        ).values('items_total')

        invoice_total = ExpressionWrapper(
            Coalesce(Subquery(invoice_items_total), 0) * (1 + F('tax_rate') / 100),
            output_field=DecimalField(max_digits=10, decimal_places=2)
        )

        return Client.objects.prefetch_related(
            Prefetch(
                'payments',
                queryset=Payment.objects.select_related('invoice').only('id', 'amount', 'status', 'invoice_id', 'client_id')
            ),
            Prefetch(
                'invoices',
                queryset=Invoice.objects.annotate(
                    invoice_total=invoice_total
                ).only('id',  'client_id')
            ),
            Prefetch(
                'address',
                queryset=Address.objects.all()
            )
        ).filter(organization_id=self.kwargs['organization_pk'])\
            .defer('created_at', 'updated_at', 'stripe_customer_id')
    
    
    def get_serializer_class(self):
        if self.request.method in ['POST']:
            return CreateClientSerializer
        elif self.request.method in ['PUT', 'PATCH']:
            return UpdateClientSerializer
        return ClientSerializer
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['organization_id'] = self.kwargs['organization_pk']
        return context
    
    
    def destroy(self, request, *args, **kwargs):
        client = self.get_object()
        if client.invoices.exists():
            return Response(
                {"detail": "Client has invoices. Please delete or transfer them first."},
                status=status.HTTP_400_BAD_REQUEST
            )
        client.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    


    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            
            # Calculate statistics
            stats = Client.objects.filter(organization_id=self.kwargs['organization_pk']).aggregate(
                total_clients=models.Count('id'),
                active_clients=models.Count('id', filter=models.Q(status=Client.ACTIVE)),
                inactive_clients=models.Count('id', filter=models.Q(status=Client.INACTIVE)),
                banned_clients=models.Count('id', filter=models.Q(status=Client.BANNED)),
            )
            
            response.data['statistics'] = stats
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    
        
    @action(detail=False, methods=['get'])
    def simple(self, request, *args, **kwargs):
        queryset = Client.objects.filter(organization_id=self.kwargs['organization_pk'], status=Client.ACTIVE).only('id', 'name', 'email', 'phone', 'status')
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = SimpleClientSerializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            return response
        
        serializer = SimpleClientSerializer(queryset, many=True)
        return Response(serializer.data)
    
    
# ================================ Client Address Viewset ================================
   
class ClientAddressViewSet(ModelViewSet):
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Address.objects.filter(client_id=self.kwargs['client_pk'])
    
    def get_serializer_class(self):
        if self.request.method in ['POST']:
            return CreateAddressSerializer
        elif self.request.method in ['PUT', 'PATCH']:
            return UpdateAddressSerializer
        return AddressSerializer
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['client_id'] = self.kwargs['client_pk']
        return context
    
    
    
#===================================== Invoice Preview Viewset ===============================

class InvoicePreviewViewSet(
    GenericViewSet,
    ListModelMixin,
    RetrieveModelMixin
):
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    
    def get_queryset(self):
        return Invoice.objects.select_related('client').prefetch_related(
            'items',
            Prefetch('payments', queryset=Payment.objects.all().select_related('invoice', 'client'))
        ).exclude(status='DRAFT').exclude(status='CANCELLED')
        

    
    
    
# ================================ Invoice Viewset ================================

class SimpleInvoiceViewSet(
    GenericViewSet,
    ListModelMixin,
    RetrieveModelMixin
):
    serializer_class = SimpleInvoiceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['invoice_number__istartswith', 'client__name__istartswith']
    
    def get_queryset(self):
        return Invoice.objects.select_related('client').prefetch_related(
            'items',
            Prefetch('payments', queryset=Payment.objects.all().select_related('invoice', 'client'))
        ).exclude(status='DRAFT').exclude(status='CANCELLED').filter(organization_id=self.kwargs['organization_pk'])

class InvoiceViewSet(
    GenericViewSet,
    CreateModelMixin,
    UpdateModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    DestroyModelMixin
):
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = [
        'invoice_number__istartswith',
        'client__name__istartswith',
        'client__phone__exact',
    ]

    ordering = ['-created_at']  # Default ordering
    permission_classes = [IsAuthenticated]
    filterset_class = InvoiceFilter
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]
    
    def get_queryset(self):
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
            
            # Get base queryset for organization with annotations
            org_queryset = annotate_invoice_calculations(
                Invoice.objects.filter(
                    organization_id=self.kwargs['organization_pk']
                )
            )
            
            # Calculate detailed statistics
            stats = {
                # Amount statistics
                'total_outstanding': org_queryset.filter(
                    status__in=['ISSUED', 'OVERDUE', 'PARTIALLY_PAID']
                ).aggregate(
                    total=models.Sum('calculated_balance', default=0)
                )['total'],
                
                'total_overdue': org_queryset.filter(
                    status='OVERDUE'
                ).aggregate(
                    total=models.Sum('calculated_balance', default=0)
                )['total'],
                
                'total_paid': org_queryset.filter(
                    status='PAID'
                ).aggregate(
                    total=models.Sum('completed_payments_sum', default=0)
                )['total']
            }
            

            
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
        
        if invoice.status not in ['ISSUED', 'OVERDUE', 'PARTIALLY_PAID']:
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
    def send(self, request, organization_pk=None, pk=None):
        """
        Send the invoice to the client and change its status to ISSUED.
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
                invoice.status = 'ISSUED'
                
                # Send the email
                email_result = send_invoice_email(invoice)
                if not email_result["success"]:
                    raise Exception(email_result["error"])
                
                invoice.save()
            
                serializer = self.get_serializer(invoice)
                return Response({
                    "detail": "Invoice has been sent to the client.",
                    "invoice": serializer.data,
                    "email_id": email_result.get("email_id")
                })
                
        except Exception as e:
            return Response(
                {"detail": f"Failed to send invoice: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
            
            
    @action(detail=True, methods=['post'])
    def cancel(self, request, organization_pk=None, pk=None, *args, **kwargs):
        invoice = self.get_object()
        if invoice.status != 'ISSUED':
            return Response(
                {"detail": "Cannot cancel invoice in non-issued status."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            invoice.status = 'CANCELLED'
            invoice.save()
            
        return Response({
            "detail": "Invoice has been cancelled.",
            "invoice": self.get_serializer(invoice).data
        })
        
        
    @action(detail=True, methods=['post'])
    def restore(self, request, organization_pk=None, pk=None, *args, **kwargs):
        invoice = self.get_object()
        if invoice.status != 'CANCELLED':
            return Response(
                {"detail": "Cannot restore invoice in non-cancelled status."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            invoice.status = 'DRAFT'
            invoice.save()
            
        return Response({
            "detail": "Invoice has been restored.",
            "invoice": self.get_serializer(invoice).data
        })
            
    def destroy(self, request, *args, **kwargs):
        invoice = self.get_object()
        if invoice.status != 'DRAFT':
            return Response(
                {"detail": "Cannot delete invoice in non-DRAFT status."},
                status=status.HTTP_400_BAD_REQUEST
            )
        invoice.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    

            
            
# ================================ Payment Viewset ================================
    
class PaymentViewSet(
    GenericViewSet,
    CreateModelMixin,
    UpdateModelMixin,
    ListModelMixin,
    RetrieveModelMixin
    ):
    pagination_class = DefaultPagination
    permission_classes = [IsAuthenticated]
    filterset_class = PaymentFilter 
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['invoice__invoice_number', 'client__name']
    ordering_fields = ['payment_date', 'amount', 'status', 'created_at']
    ordering = ['-created_at'] 
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]
    
    def get_queryset(self):
        return Payment.objects.select_related(
            'client',
            'invoice',
            'client'  # Also select client address to avoid additional queries
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
        context['request'] = self.request
        print('context', context)
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
    
    def update(self, request, *args, **kwargs):
        """
        Only allow updating payment method and notes for completed payments.
        For any other changes, the payment must be cancelled.
        """
        payment = self.get_object()
        
        # Only allow updates for completed payments
        if payment.status != 'COMPLETED':
            return Response(
                {"detail": "Only completed payments can be updated"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Only allow updating payment method and notes
        if len(request.data) != 2 or 'payment_method' not in request.data or 'notes' not in request.data:
            return Response(
                {"detail": "Only payment method and notes can be updated for completed payments. For other changes, please cancel the payment."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Check if payment method is valid
        allowed_methods = ['CASH', 'BANK_TRANSFER', 'WIRE_TRANSFER', 'CHECK']
        if payment.payment_method not in allowed_methods:
            return Response(
                {"detail": f"Cannot update {payment.payment_method} payments. Please use the refund action instead."},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().update(request, *args, **kwargs)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, organization_pk=None, pk=None):
        """
        Cancel a payment and delete it, reverting the invoice to its previous state.
        Only manual payments (CASH, BANK_TRANSFER, etc.) can be cancelled.
        Other payment types must be refunded instead.
        """
        payment = self.get_object()
        
        # Only allow cancelling completed payments
        if payment.status != 'COMPLETED':
            return Response(
                {"detail": "Can only cancel completed payments"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Only allow cancelling manual payments
        allowed_methods = ['CASH', 'BANK_TRANSFER', 'WIRE_TRANSFER', 'CHECK']
        if payment.payment_method not in allowed_methods:
            return Response(
                {"detail": f"Cannot cancel {payment.payment_method} payments. Please use the refund action instead."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        try:
            with transaction.atomic():
                # Store invoice reference before deleting payment
                invoice = payment.invoice
                
                # Delete the payment
                payment.delete()
                
                # Update invoice status
                invoice.update_status_based_on_payments()
                
                return Response(
                    {"detail": "Payment cancelled successfully"},
                    status=status.HTTP_200_OK
                )
                
        except Exception as e:
            return Response(
                {"detail": f"Failed to cancel payment: {str(e)}"},
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
            
        allowed_methods = ['CASH', 'BANK_TRANSFER', 'WIRE_TRANSFER', 'CHECK']
        if payment.payment_method not in allowed_methods:
            return Response(
                {"detail": f"Cannot refund {payment.payment_method} payments. Please use the refund action instead."},
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
            
            
            
# ================================ Stripe Payment Viewset ================================
class StripePaymentViewSet(GenericViewSet):
    """
    ViewSet for processing payments through Stripe.
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'], url_path=r'create-payment-intent/(?P<invoice_uuid>[^/.]+)')
    def create_payment_intent(self, request, organization_pk=None, invoice_uuid=None):
        """
        Create a Stripe payment intent for an invoice.
        
        Returns a client secret to be used for Stripe checkout on the frontend.
        """
        from .stripe_service import StripeService
        from datetime import timedelta
        
        try:
            # Get invoice
            invoice = Invoice.objects.get(
                organization_id=organization_pk,
                uuid=invoice_uuid
            )
            
            # Check if invoice can accept payments
            if invoice.status not in ['PENDING', 'OVERDUE', 'PARTIALLY_PAID']:
                return Response(
                    {"detail": f"Cannot create payment for invoice in {invoice.status} status"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if there's any balance due
            if invoice.due_balance <= 0:
                return Response(
                    {"detail": "Invoice has no balance due"},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            # Check if there are any pending payments for this invoice
            pending_payments_exist = invoice.payments.filter(status='PENDING').exists()
            if pending_payments_exist:
                return Response(
                    {"detail": "This invoice already has a pending payment. Please wait for the pending payment to be processed before adding a new payment."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Calculate the available amount to pay
            amount_to_pay = invoice.due_balance
            
            # Check for partial payment restrictions if amount provided
            requested_amount = request.data.get('amount')
            if requested_amount:
                try:
                    requested_amount = Decimal(str(requested_amount))
                    
                    # Check if payment is too small to be practical (e.g., less than $0.50)
                    # Skip this check for final payments that clear the balance
                    if requested_amount < Decimal('0.50') and requested_amount != amount_to_pay:
                        return Response(
                            {"detail": "Payment amount is too small. Minimum payment amount should be at least $0.50 unless it's the final payment that clears the balance."},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    
                    # Check for partial payment restrictions
                    if requested_amount < amount_to_pay:  # This would be a partial payment
                        if not invoice.allow_partial_payments:
                            return Response(
                                {"detail": f"This invoice does not allow partial payments. Payment amount must be {amount_to_pay}."},
                                status=status.HTTP_400_BAD_REQUEST
                            )
                        
                        # Check minimum payment amount for partial payments
                        if requested_amount < invoice.minimum_payment_amount:
                            return Response(
                                {"detail": f"Payment amount must be at least {invoice.minimum_payment_amount} for partial payments."},
                                status=status.HTTP_400_BAD_REQUEST
                            )
                    
                    # Ensure payment doesn't exceed available amount
                    if requested_amount > amount_to_pay:
                        requested_amount = amount_to_pay
                    
                    # Use requested amount if valid
                    amount_to_pay = requested_amount
                    
                except (ValueError, TypeError, DecimalException):
                    return Response(
                        {"detail": "Invalid payment amount"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Check for duplicate payments in the last 24 hours
            recent_time_24h = timezone.now() - timedelta(hours=24)
            duplicate_payments = Payment.objects.filter(
                invoice_id=invoice.id,
                amount=amount_to_pay,
                payment_method='CREDIT_CARD',
                created_at__gte=recent_time_24h
            ).exists()
            
            if duplicate_payments:
                return Response(
                    {"detail": "A payment with the same amount was recently recorded for this invoice. This might be a duplicate payment."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check for any payments in the last 5 minutes
            recent_time_5m = timezone.now() - timedelta(minutes=5)
            recent_payments = Payment.objects.filter(
                invoice_id=invoice.id,
                created_at__gte=recent_time_5m
            ).exists()
            
            if recent_payments:
                return Response(
                    {"detail": "A payment was recorded for this invoice in the last 5 minutes. Please wait before adding another payment."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create payment intent for the available amount
            payment_data = StripeService.create_payment_intent(
                invoice,
                return_url=request.data.get('return_url'),
                amount=amount_to_pay
            )
            
            return Response({
                "client_secret": payment_data['client_secret'],
                "payment_id": payment_data['payment_id'],
                "amount": amount_to_pay,
                "invoice_number": invoice.invoice_number
            })
            
        except Invoice.DoesNotExist:
            return Response(
                {"detail": "Invoice not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"detail": f"Error creating payment intent: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ================================ Stripe Webhook View ================================

class StripeWebhookView(APIView):
    """
    View for handling Stripe webhook events.
    """
    permission_classes = [AllowAny]  
    throttle_classes = [BurstRateThrottle] 
    
    def post(self, request, *args, **kwargs):
        from .stripe_service import StripeService, STRIPE_WEBHOOK_SECRET
        import stripe
        import logging
        import os
        
        logger = logging.getLogger(__name__)
        
        # Validate webhook secret is configured
        if not STRIPE_WEBHOOK_SECRET:
            logger.error("Stripe webhook secret not configured")
            return HttpResponse("Configuration error", status=500)
        
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        
        # Get client IP for logging and validation
        client_ip = self._get_client_ip(request)
        logger.info(f"Received webhook from IP: {client_ip}")
        
        # Optional: Validate IP against Stripe IP ranges
        # This could be enhanced with a list of Stripe IP ranges
        # if not self._is_valid_stripe_ip(client_ip):
        #    logger.warning(f"Webhook request from suspicious IP: {client_ip}")
        
        if not sig_header:
            logger.error("Missing Stripe signature header in webhook request")
            return Response(
                {"detail": "Missing Stripe signature header"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Log webhook receipt with more details
            logger.info(f"Received Stripe webhook with signature: {sig_header[:10]}... from IP: {client_ip}")
            
            # Process the webhook
            result = StripeService.handle_payment_webhook(payload, sig_header)
            
            # Log successful processing with detailed information
            logger.info(f"Successfully processed Stripe webhook type: {result.get('event_type', 'unknown')} "
                      f"with status: {result.get('status', 'unknown')}")
            
            # Return a 200 response to acknowledge receipt of the event
            return HttpResponse(status=200)
            
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid Stripe signature: {str(e)}")
            # Log suspicious activity
            logger.warning(f"Potential webhook forgery attempt from IP: {client_ip}")
            return HttpResponse(status=400)
        except Exception as e:
            logger.error(f"Error handling Stripe webhook: {str(e)}", exc_info=True)  # Include stack trace
            return HttpResponse(status=400)
    
    def _get_client_ip(self, request):
        """Get the client IP address from request headers or REMOTE_ADDR"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            # Get the first IP in case of multiple proxies
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip






class PublicInvoicePaymentView(APIView):
    """
    Public API for processing invoice payments without authentication.
    Requires a valid invoice UUID.
    """
    permission_classes = [AllowAny]
    
    def get(self, request, invoice_uuid=None, format=None):
        """
        Get invoice details and Stripe publishable key in one request.
        """
        # If no invoice_uuid provided, return error
        if invoice_uuid is None:
            return Response(
                {"detail": "Invoice UUID is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Find the invoice by its public UUID and annotate with calculations
            from .utils import annotate_invoice_calculations
            import os
            
            invoice_queryset = annotate_invoice_calculations(
                Invoice.objects.select_related('client').prefetch_related('payments')
            )
            invoice = invoice_queryset.get(uuid=invoice_uuid)
            
            # Calculate pending payments manually to ensure accuracy
            pending_payments = invoice.payments.filter(status='PENDING').aggregate(
                total=models.Sum('amount', default=0)
            )['total']
            
            # Calculate the actual amount available for payment
            available_to_pay = invoice.due_balance - pending_payments
            
            # Return both invoice details and Stripe key in one response
            data = {
                'invoice_number': invoice.invoice_number,
                'client_name': invoice.client.name,
                'invoice_total': invoice.total_amount,
                'paid_amount': invoice.paid_amount,
                'available_to_pay': available_to_pay,
                'status': invoice.status,
                'due_date': invoice.due_date,
                'pending_payments': pending_payments,
                'can_pay': (invoice.status in ['PENDING', 'OVERDUE', 'PARTIALLY_PAID'] 
                            and available_to_pay > 0),
                'days_overdue': invoice.days_overdue,
                'late_fee_percentage': invoice.late_fee_percentage,
                'late_fee_amount': invoice.late_fee_amount,
                'total_with_late_fees': invoice.total_with_late_fees,
                'allow_partial_payments': invoice.allow_partial_payments,
                'minimum_payment_amount': invoice.minimum_payment_amount,
                'payment_progress_percentage': invoice.payment_progress_percentage,
                # Include Stripe publishable key
                'publishable_key': os.environ.get('STRIPE_PUBLISHABLE_KEY')
            }
            
            return Response(data)
            
        except Invoice.DoesNotExist:
            return Response(
                {"detail": "Invoice not found"},
                status=status.HTTP_404_NOT_FOUND
            )
    
    def post(self, request, invoice_uuid, format=None):
        """
        Create a payment intent for a public invoice payment.
        """
        from .stripe_service import StripeService
        from datetime import timedelta
        
        try:
            # Find the invoice by its public UUID
            invoice = Invoice.objects.select_related('client', 'organization').get(uuid=invoice_uuid)
            
            # Check if invoice can accept payments
            if invoice.status not in ['PENDING', 'OVERDUE', 'PARTIALLY_PAID']:
                return Response(
                    {"detail": f"Cannot create payment for invoice in {invoice.status} status"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if there's any balance due
            if invoice.due_balance <= 0:
                return Response(
                    {"detail": "Invoice has no balance due"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if there are any pending payments for this invoice
            pending_payments_exist = invoice.payments.filter(status='PENDING').exists()
            if pending_payments_exist:
                return Response(
                    {"detail": "This invoice already has a pending payment. Please wait for the pending payment to be processed before adding a new payment."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Calculate the amount available to pay
            amount_to_pay = invoice.due_balance
            
            # Get requested payment amount from request, default to full available amount
            requested_amount = request.data.get('amount', amount_to_pay)
            
            # Validate payment amount
            try:
                requested_amount = Decimal(str(requested_amount))
                
                # Check if payment is too small to be practical (e.g., less than $0.50)
                # Skip this check for final payments that clear the balance
                if requested_amount < Decimal('0.50') and requested_amount != amount_to_pay:
                    return Response(
                        {"detail": "Payment amount is too small. Minimum payment amount should be at least $0.50 unless it's the final payment that clears the balance."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Check for partial payment restrictions
                if requested_amount < amount_to_pay:  # This would be a partial payment
                    if not invoice.allow_partial_payments:
                        return Response(
                            {"detail": f"This invoice does not allow partial payments. Payment amount must be {amount_to_pay}."},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    
                    # Check minimum payment amount
                    if requested_amount < invoice.minimum_payment_amount:
                        return Response(
                            {"detail": f"Payment amount must be at least {invoice.minimum_payment_amount} for partial payments."},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                
                # Ensure payment doesn't exceed available amount
                if requested_amount > amount_to_pay:
                    requested_amount = amount_to_pay
                
            except (ValueError, TypeError, DecimalException):
                return Response(
                    {"detail": "Invalid payment amount"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check for duplicate payments in the last 24 hours
            recent_time_24h = timezone.now() - timedelta(hours=24)
            duplicate_payments = Payment.objects.filter(
                invoice_id=invoice.id,
                amount=requested_amount,
                payment_method='CREDIT_CARD',
                created_at__gte=recent_time_24h
            ).exists()
            
            if duplicate_payments:
                return Response(
                    {"detail": "A payment with the same amount was recently recorded for this invoice. This might be a duplicate payment."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check for any payments in the last 5 minutes
            recent_time_5m = timezone.now() - timedelta(minutes=5)
            recent_payments = Payment.objects.filter(
                invoice_id=invoice.id,
                created_at__gte=recent_time_5m
            ).exists()
            
            if recent_payments:
                return Response(
                    {"detail": "A payment was recorded for this invoice in the last 5 minutes. Please wait before adding another payment."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create payment intent for the available amount
            payment_data = StripeService.create_payment_intent(
                invoice,
                return_url=request.data.get('return_url'),
                amount=requested_amount
            )
            
            return Response({
                "client_secret": payment_data['client_secret'],
                "payment_id": payment_data['payment_id'],
                "amount": requested_amount, 
                "invoice_number": invoice.invoice_number
            })
            
        except Invoice.DoesNotExist:
            return Response(
                {"detail": "Invoice not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error creating public payment intent: {str(e)}")
            return Response(
                {"detail": f"Error creating payment: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ================================ Bulk Invoice Item Operations ================================
class BulkInvoiceItemViewSet(GenericViewSet, CreateModelMixin, DestroyModelMixin):
    """
    ViewSet for bulk operations on invoice items.
    Supports:
    - Bulk create: POST /organizations/{organization_id}/invoices/{invoice_uuid}/bulk-items/
    - Bulk delete: DELETE /organizations/{organization_id}/invoices/{invoice_uuid}/bulk-items/?ids=1,2,3
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [BurstRateThrottle]
    
    def get_serializer_class(self):
        return BulkInvoiceItemSerializer
    
    def get_queryset(self):
        return InvoiceItem.objects.filter(
            invoice__organization_id=self.kwargs['organization_pk'],
            invoice__uuid=self.kwargs['invoice_uuid']
        )
    
    def create(self, request, *args, **kwargs):
        # Add invoice_id to the data
        data = request.data.copy()
        data['invoice_id'] = kwargs['invoice_uuid']
        
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        items = serializer.save()
        
        return Response(serializer.to_representation(items), status=status.HTTP_201_CREATED)
    
    def destroy(self, request, *args, **kwargs):
        # Get item IDs from query params
        item_ids = request.query_params.get('ids', '').split(',')
        item_ids = [id.strip() for id in item_ids if id.strip()]
        
        if not item_ids:
            return Response(
                {"detail": "No item IDs provided. Use ?ids=1,2,3 query parameter."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Filter by provided IDs and organization
        queryset = self.get_queryset().filter(id__in=item_ids)
        
        # Check if invoice is editable
        invoice = Invoice.objects.filter(
            organization_id=self.kwargs['organization_pk'],
            uuid=self.kwargs['invoice_uuid']
        ).first()
        
        if not invoice:
            return Response(
                {"detail": "Invoice not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if invoice.status not in ['DRAFT', 'PENDING']:
            return Response(
                {"detail": f"Cannot modify items for invoice in {invoice.status} status"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Delete matching items
        count = queryset.count()
        if count == 0:
            return Response(
                {"detail": "No items found matching the provided IDs"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        queryset.delete()
        
        return Response(
            {"detail": f"{count} invoice items deleted successfully"},
            status=status.HTTP_200_OK
        )
    
# ================================ Recurring Invoice Viewset ================================
class RecurringInvoiceViewSet(ModelViewSet):
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        'title',
        'client__name',
        'client__company_name',
    ]
    ordering_fields = ['start_date', 'next_generation_date', 'created_at', 'status']
    ordering = ['-created_at']
    permission_classes = [IsAuthenticated]
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]
    
    def get_queryset(self):
        return RecurringInvoice.objects.select_related('client').prefetch_related(
            'items'
        ).filter(organization_id=self.kwargs['organization_pk'])
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateRecurringInvoiceSerializer
        elif self.action in ['update', 'partial_update']:
            return UpdateRecurringInvoiceSerializer
        return RecurringInvoiceSerializer
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['organization_id'] = self.kwargs['organization_pk']
        return context
    
    @action(detail=True, methods=['post'])
    def generate_invoice(self, request, organization_pk=None, pk=None):
        """
        Manually generate a new invoice from this recurring template.
        """
        recurring_invoice = self.get_object()
        
        # Check if recurring invoice is active
        if recurring_invoice.status != 'ACTIVE':
            return Response(
                {"detail": f"Cannot generate invoice from a {recurring_invoice.status} recurring template"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                # Generate the invoice using our utility function
                invoice = self._create_invoice_from_template(recurring_invoice)
                
                # Update next generation date
                recurring_invoice.calculate_next_generation_date()
                
                # Return the created invoice
                return Response({
                    "detail": "Invoice created successfully",
                    "invoice": InvoiceSerializer(invoice).data
                }, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            return Response(
                {"detail": f"Failed to generate invoice: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _create_invoice_from_template(self, recurring_invoice):
        """
        Create a new invoice from a recurring invoice template.
        """
        # Calculate dates
        today = timezone.now().date()
        due_date = today + timedelta(days=recurring_invoice.payment_due_days)
        
        # Generate a unique invoice number
        random_suffix = str(uuid.uuid4().hex)[:6].upper()
        invoice_number = f"INV-{random_suffix}"
        while Invoice.objects.filter(invoice_number=invoice_number).exists():
            random_suffix = str(uuid.uuid4().hex)[:6].upper()
            invoice_number = f"INV-{random_suffix}"
        
        # Create the invoice
        invoice = Invoice.objects.create(
            organization_id=recurring_invoice.organization_id,
            client=recurring_invoice.client,
            invoice_number=invoice_number,
            issue_date=today,
            due_date=due_date,
            status='DRAFT',
            tax_rate=recurring_invoice.tax_rate,
            notes=f"Generated from recurring template: {recurring_invoice.title}\n\n{recurring_invoice.notes}".strip()
        )
        
        # Create all invoice items from the template
        for template_item in recurring_invoice.items.all():
            InvoiceItem.objects.create(
                invoice=invoice,
                product=template_item.product,
                description=template_item.description,
                quantity=template_item.quantity,
                unit_price=template_item.unit_price
            )
        
        return invoice
    
   
class MoncashInvoicePaymentView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]
    
    
    def get(self, request):
        return Response({"detail": "Method not allowed."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
    
    
    def post(self, request):
        """
        Create a MonCash payment for an invoice.
        """
        try:
            # Find the invoice by its UUID and organization
            invoice = Invoice.objects.select_related('client').prefetch_related('items').get(
                uuid=request.data['invoice_uuid']
            )
            
            # Check if invoice is valid
            if not invoice:
                return Response(
                    {"detail": "Invoice not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Check if invoice can accept payments
            if invoice.status not in ['ISSUED', 'OVERDUE', 'PARTIALLY_PAID']:
                return Response(
                    {"detail": f"Cannot create payment for invoice in {invoice.status} status"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Calculate the amount available to pay
            amount_to_pay = invoice.due_balance
            
            # Get requested payment amount from request, default to full available amount
            requested_amount = request.data.get('amount', amount_to_pay)
            
            # Validate payment amount
            try:
                requested_amount = Decimal(str(requested_amount))
                
                # Check if payment is too small
                if requested_amount < Decimal('0.50'):
                    return Response(
                        {"detail": "Payment amount must be at least $0.50"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Check if payment exceeds due balance
                if requested_amount > amount_to_pay:
                    return Response(
                        {"detail": f"Payment amount ${requested_amount} exceeds remaining balance ${amount_to_pay}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # If partial payments are not allowed, ensure full payment
                if not invoice.allow_partial_payments and requested_amount < amount_to_pay:
                    return Response(
                        {"detail": "This invoice requires full payment of ${amount_to_pay}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Check minimum payment amount if partial payments are allowed
                if invoice.allow_partial_payments and invoice.minimum_payment_amount:
                    if requested_amount < invoice.minimum_payment_amount:
                        return Response(
                            {"detail": f"Minimum payment amount for this invoice is ${invoice.minimum_payment_amount}"},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                
            except (ValueError, TypeError, InvalidOperation):
                return Response(
                    {"detail": "Invalid payment amount"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check for duplicate payments in last 5 minutes
            recent_time_5m = timezone.now() - timedelta(minutes=5)
            recent_payments = Payment.objects.filter(
                invoice_id=invoice.id,
                created_at__gte=recent_time_5m
            ).exists()
            
            if recent_payments:
                return Response(
                    {"detail": "A payment was recorded for this invoice in the last 5 minutes. Please wait before adding another payment."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Generate unique order ID for this payment attempt
            payment_order_id = str(uuid.uuid4())
            organization_currency = invoice.organization.currency
            
            # Convert amount to HTG if needed
            amount_for_moncash = float(requested_amount)
            if organization_currency != 'HTG':
                try:
                    amount_for_moncash = convert_currency(
                        amount=float(requested_amount),
                        from_currency=organization_currency,
                        to_currency='HTG'
                    )
                    print(f"Converted {requested_amount} {organization_currency} to {amount_for_moncash} HTG")
                except Exception as e:
                    return Response(
                        {"detail": f"Error converting payment amount to HTG: {str(e)}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            transaction_fee = get_moncash_online_transaction_fee(amount_for_moncash)
            amount_to_pay = amount_for_moncash + transaction_fee
            
            if amount_to_pay > MONCASH_MAX_AMOUNT:
                return Response(
                    {"detail": f"Payment amount ({amount_to_pay:.2f} HTG) exceeds MonCash maximum transaction limit of {MONCASH_MAX_AMOUNT:.2f} HTG. Please use a smaller amount or contact support."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                payment = process_moncash_payment(
                    request=request,
                    amount=amount_for_moncash,
                    return_url=request.data.get('return_url'),
                    order_id=payment_order_id,
                    transaction_fee=transaction_fee,
                    total_amount=amount_to_pay,
                    meta_data={
                        'invoice_id': str(invoice.id),
                        'invoice_number': invoice.invoice_number,
                        'organization_id': str(invoice.organization_id),
                        'invoice_uuid': str(request.data['invoice_uuid']),
                        'transaction_fee': str(transaction_fee),
                        'total_amount': str(amount_to_pay)
                    }
                )
                
                # Validate payment response
                if not payment:
                    return Response(
                        {"detail": "MonCash payment failed: Empty response received"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                
                # Create a pending payment record
                Payment.objects.create(
                    invoice=invoice,
                    client=invoice.client,
                    organization=invoice.organization,
                    amount=requested_amount,
                    payment_method='MON_CASH',
                    status='PENDING',
                    transaction_id=payment['transaction_id'] or payment_order_id,
                    payment_date=timezone.now().date() 
                )
                
                return Response(payment, status=status.HTTP_200_OK)
            
            except Exception as e:
                error_message = str(e)
                
                # Handle specific MonCash errors
                if "NotFoundError" in error_message:
                    return Response(
                        {"detail": "MonCash payment failed: The transaction could not be processed. The amount may exceed MonCash limits or there may be a temporary issue with the payment service."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                return Response(
                    {"detail": f"Error processing MonCash payment: {error_message}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                
        except Invoice.DoesNotExist:
            return Response(
                {"detail": "Invoice not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"detail": f"An unexpected error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class MoncashReturnView(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request, *args, **kwargs):
        """Handle MonCash payment return."""
        try:
            transaction_id = request.GET.get('transactionId')
            if not transaction_id:
                return Response({"detail": "No transaction ID provided"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Verify the payment
            verification = verify_moncash_payment(request, transaction_id)
            if not verification:
                return Response({"detail": "Payment verification failed"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Find the payment record
            try:
                payment = Payment.objects.get(transaction_id=transaction_id)
            except Payment.DoesNotExist:
                return Response({"detail": "Payment not found"}, status=status.HTTP_404_NOT_FOUND)
            
            # Consume the payment to mark it as processed
            result = consume_moncash_payment(request, transaction_id)
            if result.get('error') == 'USED':
                # Payment already consumed, just update our records if needed
                if payment.status != 'COMPLETED':
                    with transaction.atomic():
                        payment.status = 'COMPLETED'
                        payment.save()
                        payment.invoice.update_status_based_on_payments()
            elif result.get('success'):
                # Payment successfully consumed, update our records
                with transaction.atomic():
                    payment.status = 'COMPLETED'
                    payment.save()
                    payment.invoice.update_status_based_on_payments()
            else:
                return Response({"detail": "Payment consumption failed"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Redirect to the frontend success page
            frontend_url = f"{settings.FRONTEND_URL}/invoice/{payment.invoice.uuid}/payment-success"
            return redirect(frontend_url)
            
        except Exception as e:
            logger.error(f"Error processing MonCash return: {str(e)}")
            # Redirect to the frontend error page
            frontend_url = f"{settings.FRONTEND_URL}/invoice/{payment.invoice.uuid}/payment-error"
            return redirect(frontend_url)

class MoncashWebhookView(APIView):
    permission_classes = [AllowAny]  # Webhooks need to be public
    
    def post(self, request, *args, **kwargs):
        """Handle MonCash payment webhook notifications."""
        try:
            transaction_id = request.data.get('transactionId')
            if not transaction_id:
                return Response({"detail": "No transaction ID provided"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Verify and consume the payment
            verification = verify_moncash_payment(request, transaction_id)
            if not verification:
                return Response({"detail": "Payment verification failed"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Find the payment record
            try:
                payment = Payment.objects.get(transaction_id=transaction_id)
            except Payment.DoesNotExist:
                return Response({"detail": "Payment not found"}, status=status.HTTP_404_NOT_FOUND)
            
            # Consume the payment to mark it as processed
            result = consume_moncash_payment(request, transaction_id)
            if not result or not result.get('success'):
                return Response({"detail": "Payment consumption failed"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Update payment status
            with transaction.atomic():
                payment.status = 'COMPLETED'
                payment.save()
                
                # Update invoice status
                payment.invoice.update_status_based_on_payments()
            
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error processing MonCash webhook: {str(e)}")
            return Response(
                {"detail": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

def render_invoice_email(invoice):
    """
    Render the invoice email template with the provided context.
    
    Args:
        invoice: Invoice model instance containing invoice details and items
    
    Returns:
        str: Rendered HTML email content
    """
    context = {
        'invoice_number': invoice.invoice_number,
        'client_name': invoice.client.name,
        'status': invoice.status,
        'pdf_filename': f"Invoice-{invoice.invoice_number}.pdf",
        'pdf_size': '68 KB',  # You might want to calculate this dynamically
        'download_url': f"/api/invoices/{invoice.uuid}/download",  # Adjust this based on your URL structure
        'invoice_date': invoice.issue_date,
        'due_date': invoice.due_date,
        'items': [{
            'description': item.product,
            'quantity': f"{item.quantity:.1f}",
            'price': f"{item.unit_price:.2f}",
            'amount': f"{item.quantity * item.unit_price:.2f}"
        } for item in invoice.items.all()],
        'subtotal': f"{invoice.total_amount:.2f}",
        'tax_rate': invoice.tax_rate,
        'tax_amount': f"{invoice.tax_amount:.2f}",
        'total': f"{invoice.total_amount:.2f}",
        'minimum_payment': f"{invoice.minimum_payment_amount:.2f}",
        'late_fee_rate': invoice.late_fee_percentage,
        'notes': invoice.notes if invoice.notes else None,
        'payment_url': f"/invoice/{invoice.uuid}/pay",  # Adjust this based on your URL structure
        'support_email': 'support@vilangestore.com',  # You might want to make this configurable
        'current_year': datetime.datetime.now().year,
        'company_name': invoice.organization.name,  # Assuming organization has a name field
        'company_address': '123 Business Street, City, Country'  # You might want to make this configurable
    }
    
    return render_to_string('emails/issued-invoice.html', context)

def send_invoice_email(invoice, recipient_email=None):
    """
    Send an invoice email using Resend.
    
    Args:
        invoice: Invoice model instance containing invoice details and items
        recipient_email: Optional email address. If not provided, uses client's email
    
    Returns:
        dict: Response from the Resend API containing success status and details
    """
    from api.views import send_email_with_resend
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Generate email content
        html_content = render_invoice_email(invoice)
        
        # Use provided recipient email or fall back to client's email
        to_email = recipient_email or invoice.client.email
        
        # Format the organization name for the from_email
        org_name = invoice.organization.name.replace("'", "")  # Remove any apostrophes
        from_email = f"{org_name} <onboarding@resend.dev>"
        
        # Send email using Resend
        email_result = send_email_with_resend(
            to_emails='24svcs@gmail.com',
            subject=f"Invoice {invoice.invoice_number} from {org_name}",
            html_content=html_content,
            from_email=from_email
        )
        
        if not email_result.get("success", False):
            logger.error(f"Failed to send invoice email: {email_result.get('error')}")
            return {
                "success": False,
                "error": f"Failed to send email: {email_result.get('error')}"
            }
        
        logger.info(f"Successfully sent invoice email to {to_email}")
        return {
            "success": True,
            "message": "Invoice email sent successfully",
            "email_id": email_result.get("data", {}).get("id", "")
        }
        
    except Exception as e:
        logger.exception("Error sending invoice email")
        return {
            "success": False,
            "error": f"An unexpected error occurred: {str(e)}"
        }

# Example usage:
"""
# Send to client's email
result = send_invoice_email(invoice)
if result["success"]:
    print(f"Email sent successfully with ID: {result['email_id']}")
else:
    print(f"Failed to send email: {result['error']}")

# Send to specific email
result = send_invoice_email(invoice, "custom@email.com")
"""







# Expenses Views

class ExpenseModelViewset(ModelViewSet):
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['name__istartswith', 'category__iexact']
    filterset_class = ExpenseFilter
    ordering = ['-date']
    
    def get_queryset(self):
        return Expense.objects.filter(organization_id=self.kwargs['organization_pk'])
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateExpenseSerializer
        return ExpenseSerializer
    
    def get_serializer_context(self):
        return {
            'organization_id': self.kwargs['organization_pk']
        }

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            
            # Calculate expense statistics with prepaid amounts
            stats = Expense.objects.filter(
                organization_id=self.kwargs['organization_pk']
            ).aggregate(
                # Base amounts
                total_amount=models.Sum(
                    models.Case(
                        models.When(
                            expense_type='RECURRING',
                            then=models.F('amount') * models.F('prepaid_periods')
                        ),
                        default=models.F('amount'),
                        output_field=models.DecimalField()
                    )
                ),
                # Recurring expenses
                recurring_expenses=models.Count('id', filter=models.Q(expense_type='RECURRING')),
                recurring_amount=models.Sum(
                    models.Case(
                        models.When(
                            expense_type='RECURRING',
                            then=models.F('amount') * models.F('prepaid_periods')
                        ),
                        default=0,
                        output_field=models.DecimalField()
                    )
                ),
                # One-time expenses
                one_time_expenses=models.Count('id', filter=models.Q(expense_type='ONE_TIME')),
                one_time_amount=models.Sum(
                    models.Case(
                        models.When(
                            expense_type='ONE_TIME',
                            then=models.F('amount')
                        ),
                        default=0,
                        output_field=models.DecimalField()
                    )
                ),
                # Category-based statistics with prepaid amounts
                software_expenses=models.Sum(
                    models.Case(
                        models.When(
                            category='SOFTWARE',
                            then=models.Case(
                                models.When(
                                    expense_type='RECURRING',
                                    then=models.F('amount') * models.F('prepaid_periods')
                                ),
                                default=models.F('amount'),
                                output_field=models.DecimalField()
                            )
                        ),
                        default=0,
                        output_field=models.DecimalField()
                    )
                ),
                rent_expenses=models.Sum(
                    models.Case(
                        models.When(
                            category='RENT',
                            then=models.Case(
                                models.When(
                                    expense_type='RECURRING',
                                    then=models.F('amount') * models.F('prepaid_periods')
                                ),
                                default=models.F('amount'),
                                output_field=models.DecimalField()
                            )
                        ),
                        default=0,
                        output_field=models.DecimalField()
                    )
                ),
                payroll_expenses=models.Sum(
                    models.Case(
                        models.When(
                            category='PAYROLL',
                            then=models.Case(
                                models.When(
                                    expense_type='RECURRING',
                                    then=models.F('amount') * models.F('prepaid_periods')
                                ),
                                default=models.F('amount'),
                                output_field=models.DecimalField()
                            )
                        ),
                        default=0,
                        output_field=models.DecimalField()
                    )
                ),
                marketing_expenses=models.Sum(
                    models.Case(
                        models.When(
                            category='MARKETING',
                            then=models.Case(
                                models.When(
                                    expense_type='RECURRING',
                                    then=models.F('amount') * models.F('prepaid_periods')
                                ),
                                default=models.F('amount'),
                                output_field=models.DecimalField()
                            )
                        ),
                        default=0,
                        output_field=models.DecimalField()
                    )
                ),
                subscriptions_expenses=models.Sum(
                    models.Case(
                        models.When(
                            category='SUBSCRIPTIONS',
                            then=models.Case(
                                models.When(
                                    expense_type='RECURRING',
                                    then=models.F('amount') * models.F('prepaid_periods')
                                ),
                                default=models.F('amount'),
                                output_field=models.DecimalField()
                            )
                        ),
                        default=0,
                        output_field=models.DecimalField()
                    )
                )
            )
            
            # Calculate percentages
            total_amount = stats['total_amount'] or 0
            if total_amount > 0:
                stats['recurring_percentage'] = round((stats['recurring_amount'] or 0) / total_amount * 100, 2)
                stats['one_time_percentage'] = round((stats['one_time_amount'] or 0) / total_amount * 100, 2)
            else:
                stats['recurring_percentage'] = 0
                stats['one_time_percentage'] = 0
            
            response.data['statistics'] = stats
            return response
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)