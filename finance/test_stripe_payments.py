#!/usr/bin/env python
"""
Test Stripe payment processing
This test script mocks Stripe API responses to test payment processing with Stripe
"""
import os
import sys
import django
import json
import uuid
from decimal import Decimal
from unittest.mock import patch, MagicMock

# Add the project path to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'svcs.settings.dev')

try:
    django.setup()
except ModuleNotFoundError as e:
    print(f"Error: {e}")
    print("\nTry running this script from the project root directory with:")
    print("python finance/test_stripe_payments.py")
    sys.exit(1)

# Import Django models
from django.utils import timezone
from django.db import transaction
from finance.models import Organization, Client, Invoice, InvoiceItem, Payment
from finance.stripe_service import StripeService

# Mock Stripe responses
MOCK_STRIPE_CUSTOMER = {
    'id': 'cus_mock123456',
    'name': 'Elon Musk',
    'email': 'elon@example.com',
}

MOCK_PAYMENT_INTENT_CREATED = {
    'id': 'pi_mock123456',
    'client_secret': 'pi_mock123456_secret_987654',
    'amount': 11000,  # $110.00
    'currency': 'usd',
    'status': 'requires_payment_method',
    'customer': 'cus_mock123456',
}

MOCK_PAYMENT_INTENT_SUCCEEDED = {
    'id': 'pi_mock_success_123456',
    'client_secret': 'pi_mock_success_123456_secret_987654',
    'amount': 11000,  # $110.00
    'currency': 'usd',
    'status': 'succeeded',
    'customer': 'cus_mock123456',
}

MOCK_PAYMENT_INTENT_FAILED = {
    'id': 'pi_mock_failed_123456',
    'client_secret': 'pi_mock_failed_123456_secret_987654',
    'amount': 11000,  # $110.00
    'currency': 'usd',
    'status': 'failed',
    'customer': 'cus_mock123456',
    'last_payment_error': {
        'message': 'Your card was declined.',
        'code': 'card_declined',
    },
}

MOCK_WEBHOOK_PAYMENT_SUCCEEDED = {
    'type': 'payment_intent.succeeded',
    'data': {
        'object': MOCK_PAYMENT_INTENT_SUCCEEDED
    }
}

MOCK_WEBHOOK_PAYMENT_FAILED = {
    'type': 'payment_intent.payment_failed',
    'data': {
        'object': MOCK_PAYMENT_INTENT_FAILED
    }
}

def setup_test_data():
    """Create test organization, client, and invoice"""
    from core.models import User
    
    # Find or create organization
    try:
        org = Organization.objects.first()
        if not org:
            # Create test user
            user, _ = User.objects.get_or_create(
                email="test@example.com",
                defaults={
                    "first_name": "Test",
                    "last_name": "User"
                }
            )
            
            # Create organization
            org = Organization.objects.create(
                user=user,
                name="Test Organization",
                name_space="testorg",
                organization_type="ENTERPRISE",
                email="org@example.com",
                phone="+1234567890",
                description="Test organization for testing",
                industry="Technology"
            )
    except Exception as e:
        print(f"Error creating organization: {e}")
        raise
    
    # Create client with Stripe customer ID
    client, _ = Client.objects.get_or_create(
        organization=org,
        name="Elon Musk",
        defaults={
            "phone": "+1987654321",
            "email": "elon@example.com",
            "company_name": "Tesla",
            "stripe_customer_id": "cus_mock123456"
        }
    )
    
    # Create invoice
    invoice_number = f"INV-STRIPE-TEST-{uuid.uuid4().hex[:6].upper()}"
    today = timezone.now().date()
    
    invoice = Invoice.objects.create(
        organization=org,
        client=client,
        invoice_number=invoice_number,
        issue_date=today,
        due_date=today + timezone.timedelta(days=30),
        status='PENDING',
        tax_rate=Decimal('10.00')
    )
    
    # Add invoice item
    InvoiceItem.objects.create(
        invoice=invoice,
        product="Premium Package",
        description="Premium services package",
        quantity=Decimal('1.00'),
        unit_price=Decimal('100.00')
    )
    
    return org, client, invoice

@patch('stripe.Customer.list')
@patch('stripe.Customer.create')
def test_create_stripe_customer(mock_customer_create, mock_customer_list):
    """Test creating a Stripe customer"""
    print("=== Testing Create Stripe Customer ===")
    
    # Setup mocks
    mock_customer_list.return_value.data = []
    mock_customer_create.return_value = MagicMock(id='cus_mock123456')
    
    # Get test data
    _, client, _ = setup_test_data()
    
    # Test customer creation
    try:
        stripe_customer_id = StripeService.create_stripe_customer(client)
        print(f"Created stripe customer with ID: {stripe_customer_id}")
        
        # Check mock was called with correct data
        mock_customer_create.assert_called_once()
        call_args = mock_customer_create.call_args[1]
        assert call_args['name'] == client.name
        assert call_args['email'] == client.email
        
        print("✅ Create Stripe customer test passed")
        return True
    except Exception as e:
        print(f"❌ Error creating Stripe customer: {e}")
        return False

@patch('stripe.PaymentIntent.create')
@patch('finance.stripe_service.StripeService.create_stripe_customer')
def test_create_payment_intent(mock_create_customer, mock_payment_intent, payment_intent_data=None):
    """Test creating a payment intent"""
    print("\n=== Testing Create Payment Intent ===")
    
    # Setup mocks
    mock_create_customer.return_value = 'cus_mock123456'
    
    # Use the provided payment intent data or default
    if payment_intent_data is None:
        payment_intent_data = MOCK_PAYMENT_INTENT_CREATED
    
    mock_payment_intent.return_value = MagicMock(**payment_intent_data)
    
    # Get test data
    _, _, invoice = setup_test_data()
    
    # Test payment intent creation
    try:
        payment_data = StripeService.create_payment_intent(invoice)
        print(f"Created payment intent with client secret: {payment_data['client_secret']}")
        print(f"Payment ID: {payment_data['payment_id']}")
        
        # Find the payment object
        payment = Payment.objects.get(id=payment_data['payment_id'])
        print(f"Payment record created with status: {payment.status}")
        
        # Verify payment details
        assert payment.invoice == invoice
        assert payment.amount == invoice.total_amount
        assert payment.payment_method == 'CREDIT_CARD'
        assert payment.status == 'PENDING'
        assert payment.transaction_id == payment_intent_data['id']
        
        print("✅ Create payment intent test passed")
        return payment
    except Exception as e:
        print(f"❌ Error creating payment intent: {e}")
        return None

@patch('finance.stripe_service.stripe.Webhook.construct_event')
def test_webhook_payment_succeeded(mock_construct_event):
    """Test handling a webhook for a successful payment"""
    print("\n=== Testing Webhook Payment Succeeded ===")
    
    # Create a test payment with the success payment intent
    payment = test_create_payment_intent(payment_intent_data=MOCK_PAYMENT_INTENT_SUCCEEDED)
    if not payment:
        print("❌ Cannot test webhook without a valid payment")
        return False
    
    # Create webhook event matching our payment
    webhook_event = MOCK_WEBHOOK_PAYMENT_SUCCEEDED.copy()
    webhook_event['data']['object'] = MOCK_PAYMENT_INTENT_SUCCEEDED.copy()
    webhook_event['data']['object']['id'] = payment.transaction_id
    
    # Setup mock
    mock_construct_event.return_value = webhook_event
    
    # Test webhook handling
    try:
        # Call webhook handler
        result = StripeService.handle_payment_webhook(
            json.dumps(webhook_event).encode(),
            'mock_signature'
        )
        
        print(f"Webhook handled with result: {result}")
        
        # Refresh payment from database
        payment.refresh_from_db()
        print(f"Payment status after webhook: {payment.status}")
        
        # Verify payment was updated to completed
        assert payment.status == 'COMPLETED'
        
        # Verify invoice status was updated
        invoice = payment.invoice
        invoice.refresh_from_db()
        print(f"Invoice status after webhook: {invoice.status}")
        assert invoice.status in ['PAID', 'PARTIALLY_PAID']
        
        print("✅ Webhook payment succeeded test passed")
        return True
    except Exception as e:
        print(f"❌ Error handling webhook: {e}")
        return False

@patch('finance.stripe_service.stripe.Webhook.construct_event')
def test_webhook_payment_failed(mock_construct_event):
    """Test handling a webhook for a failed payment"""
    print("\n=== Testing Webhook Payment Failed ===")
    
    # Create a test payment with the failed payment intent
    payment = test_create_payment_intent(payment_intent_data=MOCK_PAYMENT_INTENT_FAILED)
    if not payment:
        print("❌ Cannot test webhook without a valid payment")
        return False
    
    # Create webhook event matching our payment
    webhook_event = MOCK_WEBHOOK_PAYMENT_FAILED.copy()
    webhook_event['data']['object'] = MOCK_PAYMENT_INTENT_FAILED.copy()
    webhook_event['data']['object']['id'] = payment.transaction_id
    
    # Setup mock
    mock_construct_event.return_value = webhook_event
    
    # Test webhook handling
    try:
        # Call webhook handler
        result = StripeService.handle_payment_webhook(
            json.dumps(webhook_event).encode(),
            'mock_signature'
        )
        
        print(f"Webhook handled with result: {result}")
        
        # Refresh payment from database
        payment.refresh_from_db()
        print(f"Payment status after webhook: {payment.status}")
        
        # Verify payment was updated to failed
        assert payment.status == 'FAILED'
        
        print("✅ Webhook payment failed test passed")
        return True
    except Exception as e:
        print(f"❌ Error handling webhook: {e}")
        return False

def run_all_tests():
    """Run all Stripe payment tests"""
    print("Testing Stripe payment processing...\n")
    
    test_create_stripe_customer()
    test_webhook_payment_succeeded()
    test_webhook_payment_failed()
    
    print("\n=== All tests completed ===")

if __name__ == "__main__":
    run_all_tests() 