#!/usr/bin/env python
"""
Direct script to test Stripe integration.
This bypasses Django shell and can be run directly:
python test_stripe_direct.py
"""
import os
import sys
import django
import uuid

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'svcs.settings.dev')
django.setup()

# Now import Django models after setup
from finance.models import Client, Invoice, Payment
from finance.stripe_service import StripeService
import stripe

def get_test_invoice():
    """Find a suitable invoice for testing"""
    invoice = Invoice.objects.filter(
        status__in=['PENDING', 'OVERDUE', 'PARTIALLY_PAID']
    ).first()
    
    if not invoice:
        print("ERROR: No suitable invoice found for testing")
        return None
    
    return invoice

def test_create_stripe_customer():
    """Test creating a Stripe customer from a client"""
    print("\n=== Testing Create Stripe Customer ===")
    
    # Get a client
    client = Client.objects.filter(email__isnull=False).first()
    if not client:
        print("ERROR: No client with email found")
        return False
    
    print(f"Using client: {client.name} (ID: {client.id}, Email: {client.email})")
    
    try:
        # Create customer in Stripe
        customer_id = StripeService.create_stripe_customer(client)
        print(f"Created Stripe customer ID: {customer_id}")
        
        # Verify customer
        customer = stripe.Customer.retrieve(customer_id)
        print(f"Verified customer: {customer.name} ({customer.email})")
        
        return True
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return False

def test_create_payment_intent():
    """Test creating a payment intent for an invoice"""
    print("\n=== Testing Create Payment Intent ===")
    
    invoice = get_test_invoice()
    if not invoice:
        return False
    
    print(f"Using invoice #{invoice.invoice_number} (ID: {invoice.id}, UUID: {invoice.uuid})")
    print(f"Due balance: ${invoice.due_balance}")
    print(f"Client: {invoice.client.name}")
    
    try:
        # Create payment intent
        payment_data = StripeService.create_payment_intent(invoice)
        
        print("\nPayment Intent created:")
        print(f"Payment Intent ID: {payment_data['payment_intent'].id}")
        print(f"Client Secret: {payment_data['client_secret']}")
        
        # Verify payment record was created
        payment = Payment.objects.get(id=payment_data['payment_id'])
        print(f"\nPayment record created in database:")
        print(f"Payment ID: {payment.id}")
        print(f"Status: {payment.status}")
        print(f"Amount: ${payment.amount}")
        print(f"Transaction ID: {payment.transaction_id}")
        
        return payment.id
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return False

def test_webhook_handler(payment_id=None):
    """Test webhook handler with a simulated event"""
    print("\n=== Testing Webhook Handler ===")
    
    if payment_id:
        try:
            payment = Payment.objects.get(id=payment_id)
        except Payment.DoesNotExist:
            print(f"ERROR: Payment with ID {payment_id} not found")
            return False
    else:
        # Get any pending payment with a transaction_id
        payments = Payment.objects.filter(
            transaction_id__isnull=False,
            status='PENDING'
        )
        
        if not payments.exists():
            print("ERROR: No payments with transaction_id found")
            return False
            
        # Get the most recent one
        payment = payments.order_by('-created_at').first()
    
    if not payment.transaction_id:
        print(f"ERROR: Payment {payment.id} has no transaction_id")
        return False
    
    print(f"Using payment ID: {payment.id}")
    print(f"Transaction ID: {payment.transaction_id}")
    print(f"Current status: {payment.status}")
    print(f"Invoice: {payment.invoice.invoice_number}")
    
    try:
        # Create mock event
        mock_event = {
            'type': 'payment_intent.succeeded',
            'data': {
                'object': {
                    'id': payment.transaction_id,
                    'status': 'succeeded'
                }
            }
        }
        
        print("\nSimulating payment_intent.succeeded webhook event")
        result = StripeService._handle_payment_succeeded(mock_event)
        
        print(f"Webhook handler result: {result}")
        
        # Verify payment was updated
        payment.refresh_from_db()
        print(f"\nPayment status after webhook: {payment.status}")
        print(f"Invoice status after webhook: {payment.invoice.status}")
        
        return True
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return False

def main():
    """Run all tests"""
    print("=== STARTING STRIPE INTEGRATION TESTS ===")
    
    results = {}
    
    # Test 1: Create customer
    results['create_customer'] = test_create_stripe_customer()
    
    # Test 2: Create payment intent
    payment_id = test_create_payment_intent()
    results['create_payment_intent'] = bool(payment_id)
    
    # Test 3: Webhook handling
    if payment_id:
        results['webhook_handling'] = test_webhook_handler(payment_id)
    else:
        results['webhook_handling'] = test_webhook_handler()
    
    # Print summary
    print("\n=== TEST RESULTS ===")
    for test, result in results.items():
        print(f"{test}: {'PASSED' if result else 'FAILED'}")
    
    success = all(results.values())
    print(f"\nOverall result: {'PASSED' if success else 'FAILED'}")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main()) 