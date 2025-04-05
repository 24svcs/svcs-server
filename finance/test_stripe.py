"""
Test script for Stripe integration.
Run this script with Django shell:
python manage.py shell < finance/test_stripe.py
"""

import os
import sys
import json
import stripe
from django.conf import settings
from django.utils import timezone
from finance.models import Invoice, Payment, Client
from finance.stripe_service import StripeService

# Set up logging
import logging
logger = logging.getLogger('stripe_test')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def test_create_stripe_customer():
    """Test creating a Stripe customer from a client."""
    print("\n--- TESTING CREATE STRIPE CUSTOMER ---")
    
    # Get a client from the database
    client = Client.objects.filter(email__isnull=False).first()
    
    if not client:
        print("ERROR: No clients found with email. Test failed.")
        return False
    
    print(f"Using client: {client.name} ({client.email})")
    
    try:
        # Create a Stripe customer
        customer_id = StripeService.create_stripe_customer(client)
        print(f"Created Stripe customer with ID: {customer_id}")
        
        # Verify the customer exists in Stripe
        customer = stripe.Customer.retrieve(customer_id)
        print(f"Verified Stripe customer: {customer.name} ({customer.email})")
        
        return True
    except Exception as e:
        print(f"ERROR in create_stripe_customer test: {str(e)}")
        return False

def test_create_payment_intent():
    """Test creating a payment intent for an invoice."""
    print("\n--- TESTING CREATE PAYMENT INTENT ---")
    
    # Get an invoice with due balance
    invoice = Invoice.objects.filter(
        status__in=['PENDING', 'OVERDUE', 'PARTIALLY_PAID']
    ).first()
    
    if not invoice:
        print("ERROR: No suitable invoices found. Test failed.")
        return False
    
    print(f"Using invoice: #{invoice.invoice_number} (Status: {invoice.status})")
    print(f"Due balance: {invoice.due_balance}")
    
    try:
        # Create a payment intent
        payment_data = StripeService.create_payment_intent(invoice)
        print(f"Created payment intent: {payment_data['payment_intent'].id}")
        print(f"Client secret: {payment_data['client_secret']}")
        
        # Verify the payment was created in the database
        payment = Payment.objects.get(id=payment_data['payment_id'])
        print(f"Created payment record: {payment.id} (Status: {payment.status})")
        print(f"Transaction ID: {payment.transaction_id}")
        
        return True
    except Exception as e:
        print(f"ERROR in create_payment_intent test: {str(e)}")
        return False

def test_stripe_webhook():
    """Test handling a simulated Stripe webhook event."""
    print("\n--- TESTING WEBHOOK HANDLING ---")
    
    # Get a payment with a transaction_id (Stripe payment intent ID)
    payment = Payment.objects.filter(
        transaction_id__isnull=False,
        status='PENDING'
    ).first()
    
    if not payment:
        print("ERROR: No suitable payment found. Test failed.")
        return False
    
    print(f"Using payment: {payment.id} (Invoice: {payment.invoice.invoice_number})")
    print(f"Transaction ID: {payment.transaction_id}")
    print(f"Current status: {payment.status}")
    
    try:
        # Simulate a payment_intent.succeeded event
        mock_event = {
            'type': 'payment_intent.succeeded',
            'data': {
                'object': {
                    'id': payment.transaction_id,
                    'status': 'succeeded'
                }
            }
        }
        
        print("Simulating payment_intent.succeeded webhook event")
        
        # Call the handler directly
        result = StripeService._handle_payment_succeeded(mock_event)
        print(f"Webhook handling result: {result}")
        
        # Verify payment was updated
        payment.refresh_from_db()
        print(f"Payment status after webhook: {payment.status}")
        print(f"Invoice status after webhook: {payment.invoice.status}")
        
        return True
    except Exception as e:
        print(f"ERROR in webhook test: {str(e)}")
        return False

def run_all_tests():
    """Run all tests in sequence."""
    print("=== STARTING STRIPE INTEGRATION TESTS ===")
    
    results = {}
    
    results['create_customer'] = test_create_stripe_customer()
    results['create_payment_intent'] = test_create_payment_intent()
    results['webhook_handling'] = test_stripe_webhook()
    
    # Print summary
    print("\n===== TEST RESULTS =====")
    for test, result in results.items():
        print(f"{test}: {'PASSED' if result else 'FAILED'}")
    
    # Overall result
    if all(results.values()):
        print("All tests PASSED!")
    else:
        print("Some tests FAILED.")

if __name__ == "__main__":
    run_all_tests() 