import stripe
import logging
import os

from django.utils import timezone
from .models import  Payment
from decimal import Decimal
import json

logger = logging.getLogger(__name__)

stripe.api_key = os.environ.get('STRIPE_GLOBAL_API_KEY')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')

class StripeService:
    """
    Service class for handling Stripe payment integrations.
    """
    
    @staticmethod
    def create_stripe_customer(client):
        """
        Create a Stripe customer for a client if they don't have one already.
        
        Args:
            client (Client): The client model to create a Stripe customer for
            
        Returns:
            str: The Stripe customer ID
        """
        try:
            # Try to find if customer exists in Stripe by metadata
            existing_customers = stripe.Customer.list(
                email=client.email,
                limit=1
            )
            
            if existing_customers and existing_customers.data:
                # Customer exists in Stripe
                return existing_customers.data[0].id
            
            # Create customer in Stripe
            customer_data = {
                'name': client.name,
                'email': client.email,
                'phone': str(client.phone) if client.phone else None,
                'metadata': {
                    'client_id': client.id,
                    'organization_id': client.organization_id
                }
            }
            
            if client.company_name:
                customer_data['description'] = f"Company: {client.company_name}"
            
            stripe_customer = stripe.Customer.create(**customer_data)
            
            return stripe_customer.id
            
        except Exception as e:
            logger.error(f"Error creating Stripe customer: {str(e)}")
            raise
    
    @staticmethod
    def create_payment_intent(invoice, return_url=None, payment_method_types=None, amount=None):
        """
        Create a payment intent for an invoice.
        
        Args:
            invoice (Invoice): The invoice to create a payment intent for
            return_url (str, optional): URL to redirect after payment
            payment_method_types (list, optional): List of payment method types to accept
            amount (Decimal, optional): Specific amount to charge, defaults to invoice.due_balance
            
        Returns:
            dict: The payment intent object
        """
        try:
            # Get or create Stripe customer
            client = invoice.client
            customer_id = StripeService.create_stripe_customer(client)
            
            if not payment_method_types:
                payment_method_types = ['card']
            
            # Use the provided amount or fall back to the full invoice balance
            payment_amount = amount if amount is not None else invoice.due_balance
            
            # Calculate amount in cents (Stripe uses smallest currency unit)
            # For USD, that's cents, so we multiply by 100
            amount_in_cents = int((payment_amount.quantize(Decimal('0.01')) * 100))
            
            # Create payment intent
            intent = stripe.PaymentIntent.create(
                amount=amount_in_cents,
                currency='usd',  
                customer=customer_id,
                payment_method_types=payment_method_types,
                description=f"Payment for Invoice #{invoice.invoice_number}",
                metadata={
                    'invoice_id': invoice.id,
                    'invoice_number': invoice.invoice_number,
                    'client_id': client.id,
                    'organization_id': invoice.organization_id
                }
            )
            
            # Create a pending payment record
            payment = Payment.objects.create(
                organization_id=invoice.organization_id,
                client=client,
                invoice=invoice,
                amount=payment_amount,
                payment_date=timezone.now().date(), 
                payment_method='CREDIT_CARD',
                status='PENDING',
                transaction_id=intent.id,
                notes=f"Stripe payment intent: {intent.id}"
            )
            
            return {
                'payment_intent': intent,
                'client_secret': intent.client_secret,
                'payment_id': payment.id
            }
            
        except Exception as e:
            logger.error(f"Error creating payment intent: {str(e)}")
            raise
    
    @staticmethod
    def handle_payment_webhook(payload, signature):
        """
        Handle Stripe webhook events for payment updates.
        
        Args:
            payload (bytes): The raw webhook payload
            signature (str): The Stripe signature header
            
        Returns:
            dict: A response with details of the handled event
        """
        try:
            # Check if we're in test mode (development environment)
            # This allows bypassing signature verification during development
            is_test_mode = os.environ.get('STRIPE_WEBHOOK_TEST_MODE', 'false').lower() == 'true'
            
            if is_test_mode:
                # For development/testing, allow constructing event without signature verification
                logger.warning("STRIPE_WEBHOOK_TEST_MODE is enabled. Bypassing signature verification.")
                try:
                    event = json.loads(payload)
                except Exception:
                    logger.error("Failed to parse webhook payload in test mode")
                    raise
            else:
                # Production mode - enforce signature verification
                event = stripe.Webhook.construct_event(
                    payload, signature, STRIPE_WEBHOOK_SECRET
                )
            
            # Handle different event types
            if event['type'] == 'payment_intent.succeeded':
                return StripeService._handle_payment_succeeded(event)
            elif event['type'] == 'payment_intent.payment_failed':
                return StripeService._handle_payment_failed(event)
            elif event['type'] == 'charge.refunded':
                return StripeService._handle_charge_refunded(event)
            
            return {'status': 'ignored', 'event_type': event['type']}
            
        except stripe.error.SignatureVerificationError:
            logger.error("Invalid signature in Stripe webhook")
            raise
        except Exception as e:
            logger.error(f"Error handling Stripe webhook: {str(e)}")
            raise
    
    @staticmethod
    def _handle_payment_succeeded(event):
        """
        Handle a payment_intent.succeeded event.
        
        Args:
            event (dict): The Stripe event object
            
        Returns:
            dict: Status and details of the handled event
        """
        payment_intent = event['data']['object']
        transaction_id = payment_intent['id']
        
        # Log the raw payment intent data for debugging
        logger.debug(f"Handling payment_intent.succeeded for {transaction_id}")
        logger.debug(f"Payment intent data: {payment_intent}")
        
        try:
            # Find the payment record
            payment = Payment.objects.get(transaction_id=transaction_id)
            
            # Verify the payment amount matches what's in Stripe 
            # (in cents, divide by 100 to get dollars)
            stripe_amount = Decimal(payment_intent['amount']) / 100
            
            # Log if there's a discrepancy and use the Stripe amount
            if payment.amount != stripe_amount:
                logger.warning(
                    f"Payment amount mismatch: DB has {payment.amount}, "
                    f"Stripe has {stripe_amount} for transaction {transaction_id}. "
                    f"Using the Stripe amount as source of truth."
                )
                # Update the payment amount to match Stripe (the source of truth)
                original_amount = payment.amount
                payment.amount = stripe_amount
                payment.notes += f"\nPayment amount updated from {original_amount} to {stripe_amount} to match Stripe records."
            
            # Update payment status
            payment.status = 'COMPLETED'
            payment.payment_date = timezone.now().date()
            payment.save()
            
            # Log the successful payment
            logger.info(
                f"Payment {payment.id} for invoice {payment.invoice.invoice_number} "
                f"completed successfully. Amount: {payment.amount}"
            )
            
            return {
                'status': 'success',
                'payment_id': payment.id,
                'invoice_id': payment.invoice.id
            }
        except Payment.DoesNotExist:
            logger.error(f"Payment not found for transaction ID: {transaction_id}")
            return {'status': 'error', 'error': 'Payment not found'}
    
    @staticmethod
    def _handle_payment_failed(event):
        """
        Handle a payment_intent.payment_failed event.
        
        Args:
            event (dict): The Stripe event object
            
        Returns:
            dict: Status and details of the handled event
        """
        payment_intent = event['data']['object']
        transaction_id = payment_intent['id']
        
        try:
            # Find the payment record
            payment = Payment.objects.get(transaction_id=transaction_id)
            
            # Update payment status
            payment.status = 'FAILED'
            payment.notes += f"\nPayment failed: {payment_intent.get('last_payment_error', {}).get('message', 'Unknown error')}"
            payment.save()
            
            return {
                'status': 'failed',
                'payment_id': payment.id,
                'invoice_id': payment.invoice.id
            }
        except Payment.DoesNotExist:
            logger.error(f"Payment not found for transaction ID: {transaction_id}")
            return {'status': 'error', 'error': 'Payment not found'}
    
    @staticmethod
    def _handle_charge_refunded(event):
        """
        Handle a charge.refunded event.
        
        Args:
            event (dict): The Stripe event object
            
        Returns:
            dict: Status and details of the handled event
        """
        charge = event['data']['object']
        payment_intent_id = charge.get('payment_intent')
        
        if not payment_intent_id:
            return {'status': 'ignored', 'reason': 'No payment intent ID'}
        
        try:
            # Find the payment record
            payment = Payment.objects.get(transaction_id=payment_intent_id)
            
            # Update payment status
            payment.status = 'REFUNDED'
            payment.notes += f"\nRefunded on {timezone.now().date()}"
            payment.save()
            
            return {
                'status': 'refunded',
                'payment_id': payment.id,
                'invoice_id': payment.invoice.id
            }
        except Payment.DoesNotExist:
            logger.error(f"Payment not found for transaction ID: {payment_intent_id}")
            return {'status': 'error', 'error': 'Payment not found'} 