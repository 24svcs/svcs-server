from rest_framework.viewsets import ModelViewSet, GenericViewSet
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin
import logging

from .serializers import (
    Client, ClientSerializer, CreateClientSerializer,
    Invoice, InvoiceSerializer, CreateInvoiceSerializer, UpdateInvoiceSerializer,
    Payment, PaymentSerializer, CreatePaymentSerializer, UpdatePaymentSerializer,
    InvoiceItem, BulkInvoiceItemSerializer,
    RecurringInvoice, RecurringInvoiceSerializer, CreateRecurringInvoiceSerializer, UpdateRecurringInvoiceSerializer,

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
from api.throttling import BurstRateThrottle, SustainedRateThrottle
import uuid
from .serializers import ClientAddressSerializer, Address

logger = logging.getLogger(__name__)


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
        
        address_queryset = Address.objects.select_related('client') 
        
        return Client.objects.prefetch_related(
            Prefetch('invoices', queryset=invoice_queryset),
            Prefetch('payments', queryset=payment_queryset),
            # Prefetch('addresses', queryset=address_queryset)
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
    
    
# ================================ Client Address Viewset ================================
   
class ClientAddressViewSet(ModelViewSet):
    serializer_class = ClientAddressSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Address.objects.filter(client_id=self.kwargs['client_pk'])
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['client_id'] = self.kwargs['client_pk']
        return context
    
    
    
    
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
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]
    
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
            
            # Calculate total pending payments
            pending_payments_total = invoice.payments.filter(status='PENDING').aggregate(
                total=models.Sum('amount', default=0)
            )['total']
            
            # Calculate the available amount to pay
            available_to_pay = invoice.due_balance - pending_payments_total
            
            if available_to_pay <= 0:
                return Response(
                    {"detail": "This invoice already has pending payments covering the full amount. Please wait for those payments to be processed."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create payment intent for the available amount
            payment_data = StripeService.create_payment_intent(
                invoice,
                return_url=request.data.get('return_url'),
                amount=available_to_pay
            )
            
            return Response({
                "client_secret": payment_data['client_secret'],
                "payment_id": payment_data['payment_id'],
                "available_to_pay": available_to_pay,
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


from rest_framework.views import APIView
from django.http import HttpResponse
from rest_framework.permissions import AllowAny


class StripeWebhookView(APIView):
    """
    View for handling Stripe webhook events.
    """
    permission_classes = [AllowAny]  # Stripe needs to access this endpoint without authentication
    
    def post(self, request, *args, **kwargs):
        from .stripe_service import StripeService, STRIPE_WEBHOOK_SECRET
        import stripe
        import logging
        
        logger = logging.getLogger(__name__)
        
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        
        if not sig_header:
            logger.error("Missing Stripe signature header in webhook request")
            return Response(
                {"detail": "Missing Stripe signature header"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Log webhook receipt
            logger.info(f"Received Stripe webhook with signature: {sig_header[:10]}...")
            
            # Process the webhook
            result = StripeService.handle_payment_webhook(payload, sig_header)
            
            # Log successful processing
            logger.info(f"Successfully processed Stripe webhook: {result}")
            
            # Return a 200 response to acknowledge receipt of the event
            return HttpResponse(status=200)
            
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid Stripe signature: {str(e)}")
            return HttpResponse(status=400)
        except Exception as e:
            logger.error(f"Error handling Stripe webhook: {str(e)}")
            return HttpResponse(status=400)


class PublicInvoicePaymentView(APIView):
    """
    Public API for processing invoice payments without authentication.
    Requires a valid invoice UUID and a payment token.
    """
    permission_classes = [AllowAny]
    
    def get(self, request, invoice_uuid=None, format=None):
        """
        Get invoice details for a public payment page or serve the HTML template.
        """
        # Check if the request is from a browser looking for HTML
        wants_html = 'text/html' in request.headers.get('Accept', '')
        
        # If no invoice_uuid provided or browser requests HTML, serve the HTML template
        if invoice_uuid is None or wants_html:
            from django.http import HttpResponse
            from django.conf import settings
            import os
            
            # Get the HTML template path
            template_path = os.path.join(settings.BASE_DIR, 'static', 'templates', 'invoice_payment.html')
            
            try:
                with open(template_path, 'r') as f:
                    html_content = f.read()
                return HttpResponse(html_content, content_type='text/html')
            except FileNotFoundError:
                return Response(
                    {"detail": "Payment template not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # If invoice_uuid provided and API request, return the invoice details as JSON
        try:
            # Find the invoice by its public UUID and annotate with calculations
            from .utils import annotate_invoice_calculations
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
            
            # Only return minimal information needed for payment
            data = {
                'invoice_number': invoice.invoice_number,
                'client_name': invoice.client.name,
                'invoice_total': invoice.total_amount,
                'paid_amount': invoice.paid_amount,
                'available_to_pay': available_to_pay,  # Renamed from 'amount' for clarity
                'status': invoice.status,
                'due_date': invoice.due_date,
                'pending_payments': pending_payments,
                'can_pay': (invoice.status in ['PENDING', 'OVERDUE', 'PARTIALLY_PAID'] 
                            and available_to_pay > 0)
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
        import os
        
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
            
            # Calculate total pending payments
            pending_payments_total = invoice.payments.filter(status='PENDING').aggregate(
                total=models.Sum('amount', default=0)
            )['total']
            
            # Calculate the available amount to pay
            available_to_pay = invoice.due_balance - pending_payments_total
            
            if available_to_pay <= 0:
                return Response(
                    {"detail": "This invoice already has pending payments covering the full amount. Please wait for those payments to be processed."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create payment intent for the available amount
            payment_data = StripeService.create_payment_intent(
                invoice,
                return_url=request.data.get('return_url'),
                amount=available_to_pay
            )
            
            return Response({
                "client_secret": payment_data['client_secret'],
                "payment_id": payment_data['payment_id'],
                "available_to_pay": available_to_pay,
                "invoice_number": invoice.invoice_number,
                "publishable_key": os.environ.get('STRIPE_PUBLISHABLE_KEY')
            })
            
        except Invoice.DoesNotExist:
            return Response(
                {"detail": "Invoice not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger = logging.getLogger(__name__)
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
    
   

    
    
    
    