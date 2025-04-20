from rest_framework.viewsets import ModelViewSet, GenericViewSet
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin, UpdateModelMixin, ListModelMixin, RetrieveModelMixin
import logging
from decimal import Decimal, DecimalException


from .serializer import (
    Invoice, InvoiceSerializer, CreateInvoiceSerializer, UpdateInvoiceSerializer,
    Payment, PaymentSerializer, CreatePaymentSerializer, UpdatePaymentSerializer,
    InvoiceItem, BulkInvoiceItemSerializer,
    RecurringInvoice, RecurringInvoiceSerializer, CreateRecurringInvoiceSerializer, UpdateRecurringInvoiceSerializer,

)
from rest_framework.permissions import IsAuthenticated
from api.pagination import DefaultPagination
from django_filters.rest_framework import DjangoFilterBackend
from .filters import ClientFilter, InvoiceFilter, PaymentFilter
from django.db import models, transaction
from django.db.models import Q, Sum, Count
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
from django.db.models import F, Prefetch
from finance.serializers.client_serializers import  Client, ClientSerializer, CreateClientSerializer, UpdateClientSerializer, SimpleClientSerializer
from finance.serializers.address_serializers import (
    Address,
    AddressSerializer,
    CreateAddressSerializer,
    UpdateAddressSerializer
)
from finance.serializers.invoice_serializers import SimpleInvoiceSerializer
logger = logging.getLogger(__name__)


class ClientModelViewset(ModelViewSet):
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = ClientFilter
    search_fields = ['name__istartswith', 'email__istartswith', 'phone__exact', 'tax_number__exact']
    ordering_fields = ['name']

    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Client.objects.prefetch_related(
            Prefetch('payments', queryset=Payment.objects.select_related('invoice')),
            Prefetch('invoices', queryset=Invoice.objects.prefetch_related('items')),
        ).filter(organization_id=self.kwargs['organization_pk'])
    
    serializer_class = ClientSerializer
    
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
            
            current_date = timezone.now()
            thirty_days_ago = current_date - timedelta(days=30)
            
            # Calculate statistics
            stats = Client.objects.filter(organization_id=self.kwargs['organization_pk']).aggregate(
                total_clients=models.Count('id'),
                active_clients=models.Count('id', filter=models.Q(status=Client.ACTIVE)),
                inactive_clients=models.Count('id', filter=models.Q(status=Client.INACTIVE)),
                banned_clients=models.Count('id', filter=models.Q(status=Client.BANNED)),
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
        ).exclude(status='DRAFT')
        

    
    
    
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
        ).exclude(status='DRAFT').filter(organization_id=self.kwargs['organization_pk'])

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
                invoice.status = 'ISSUED'
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
    
   

    
    
    
    