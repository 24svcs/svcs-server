#!/usr/bin/env python
"""
Test script for partial payment functionality.
This tests the new invoice enhancements for partial payments and late fees.
"""
import os
import sys
import django
import uuid
from decimal import Decimal
from datetime import timedelta

# Add the project path to Python path
# This ensures the script can find modules regardless of where it's run from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'svcs.settings.dev')

try:
    django.setup()
except ModuleNotFoundError as e:
    print(f"Error: {e}")
    print("\nTry running this script from the project root directory with:")
    print("python finance/test_partial_payments.py")
    sys.exit(1)

# Import Django models
from django.utils import timezone
from django.db import transaction
from finance.models import Organization, Client, Invoice, InvoiceItem, Payment
from finance.serializers import CreatePaymentSerializer
from rest_framework.exceptions import ValidationError

def setup_test_invoice():
    """Create a test invoice with partial payment settings."""
    print("\n=== Creating Test Invoice ===")
    
    # Get the first organization
    org = Organization.objects.first()
    if not org:
        print("No organization found. Please create an organization first.")
        return None
        
    # Get a client for this organization
    client = Client.objects.filter(organization=org).first()
    if not client:
        print("No client found. Please create a client first.")
        return None
    
    # Create a new invoice with partial payments allowed
    invoice_number = f"INV-TEST-PARTIAL-{uuid.uuid4().hex[:6].upper()}"
    today = timezone.now().date()
    due_date = today + timedelta(days=30)
    
    print(f"Creating invoice {invoice_number} for client {client.name}")
    
    invoice = Invoice.objects.create(
        organization=org,
        client=client,
        invoice_number=invoice_number,
        issue_date=today,
        due_date=due_date,
        status='PENDING',
        tax_rate=Decimal('10.00'),
        allow_partial_payments=True,
        minimum_payment_amount=Decimal('25.00')
    )
    
    # Add an invoice item
    item = InvoiceItem.objects.create(
        invoice=invoice,
        product="Test Product",
        description="Test product for partial payment testing",
        quantity=Decimal('1.00'),
        unit_price=Decimal('100.00')
    )
    
    print(f"Invoice created with ID: {invoice.id}, UUID: {invoice.uuid}")
    print(f"Total amount: ${invoice.total_amount}")
    print(f"Minimum payment amount: ${invoice.minimum_payment_amount}")
    
    return invoice

def create_test_payment(invoice, amount, payment_method, notes):
    """Helper function to create a test payment directly."""
    payment = Payment.objects.create(
        organization=invoice.organization,
        client=invoice.client,
        invoice=invoice,
        amount=amount,
        payment_date=timezone.now().date(),
        payment_method=payment_method,
        status='PENDING',
        notes=notes
    )
    return payment

def test_partial_payment_validation():
    """Test validation rules for partial payments."""
    print("\n=== Testing Partial Payment Validation ===")
    
    invoice = setup_test_invoice()
    if not invoice:
        return False
    
    # Test cases to try
    test_cases = [
        {
            "name": "Valid full payment",
            "amount": Decimal('110.00'),
            "should_succeed": True
        },
        {
            "name": "Valid partial payment at minimum",
            "amount": invoice.minimum_payment_amount,
            "should_succeed": True
        },
        {
            "name": "Valid partial payment above minimum",
            "amount": invoice.minimum_payment_amount + Decimal('10.00'),
            "should_succeed": True
        },
        {
            "name": "Invalid payment below minimum",
            "amount": invoice.minimum_payment_amount - Decimal('1.00'),
            "should_succeed": False
        },
        {
            "name": "Invalid payment above total",
            "amount": invoice.total_amount + Decimal('10.00'),
            "should_succeed": False
        },
        {
            "name": "Invalid zero payment",
            "amount": Decimal('0.00'),
            "should_succeed": False
        }
    ]
    
    # Run test cases
    results = {}
    
    for case in test_cases:
        print(f"\nTesting: {case['name']}")
        print(f"  Amount: ${case['amount']}")
        
        # Create a serializer instance with test data
        data = {
            'invoice_id': invoice.id,
            'amount': case['amount'],
            'payment_method': 'BANK_TRANSFER',
            'notes': f"Test payment - {case['name']}"
        }
        
        serializer = CreatePaymentSerializer(data=data, context={'organization_id': invoice.organization_id})
        
        try:
            # Validate the serializer data
            is_valid = serializer.is_valid()
            if not is_valid:
                print(f"  Validation errors: {serializer.errors}")
                success = not case['should_succeed']
            else:
                # Try to save the payment in a transaction that we'll roll back
                with transaction.atomic():
                    payment = serializer.save()
                    print(f"  Payment created: ID {payment.id}, Status: {payment.status}")
                    success = case['should_succeed']
                    # Roll back the transaction to keep the database clean
                    transaction.set_rollback(True)
        except ValidationError as e:
            print(f"  Validation error: {e}")
            success = not case['should_succeed']
        except Exception as e:
            print(f"  Unexpected error: {e}")
            success = False
        
        results[case['name']] = success
        print(f"  Result: {'PASSED' if success else 'FAILED'}")
    
    # Test disabling partial payments
    print("\n=== Testing Disabling Partial Payments ===")
    
    try:
        # Set allow_partial_payments to False and minimum_payment_amount to 0
        invoice.allow_partial_payments = False
        invoice.minimum_payment_amount = Decimal('0.00')
        invoice.save()
        
        # Try to create a payment for full amount
        payment = create_test_payment(
            invoice=invoice,
            amount=Decimal('110.00'),
            payment_method='CASH',
            notes='Full payment with partial payments disabled'
        )
        
        print(f"  Full payment created: ID {payment.id}, Status: {payment.status}")
        print("  Result: PASSED")
    except ValidationError as e:
        print(f"  Validation errors: {e}")
        print("  Result: FAILED")
    
    # Print summary
    print("\n=== Test Results ===")
    all_passed = True
    for test, passed in results.items():
        print(f"{test}: {'PASSED' if passed else 'FAILED'}")
        if not passed:
            all_passed = False
    
    print(f"\nOverall result: {'PASSED' if all_passed else 'FAILED'}")
    return all_passed

def test_late_fee_application():
    """Test automatic application of late fees."""
    print("\n=== Testing Late Fee Application ===")
    
    # Get the first organization
    org = Organization.objects.first()
    if not org:
        print("No organization found. Please create an organization first.")
        return False
        
    # Get a client for this organization
    client = Client.objects.filter(organization=org).first()
    if not client:
        print("No client found. Please create a client first.")
        return False
    
    # Create an invoice that's already overdue
    invoice_number = f"INV-TEST-LATE-{uuid.uuid4().hex[:6].upper()}"
    today = timezone.now().date()
    past_date = today - timedelta(days=10)  # 10 days ago
    
    print(f"Creating overdue invoice {invoice_number} for client {client.name}")
    
    invoice = Invoice.objects.create(
        organization=org,
        client=client,
        invoice_number=invoice_number,
        issue_date=past_date,
        due_date=past_date + timedelta(days=5),  # 5 days after issue, so 5 days overdue
        status='PENDING',  # Start as pending, should become overdue
        tax_rate=Decimal('10.00'),
        late_fee_percentage=Decimal('5.00')  # 5% late fee
    )
    
    # Add an invoice item
    item = InvoiceItem.objects.create(
        invoice=invoice,
        product="Test Product",
        description="Test product for late fee testing",
        quantity=Decimal('1.00'),
        unit_price=Decimal('100.00')
    )
    
    print(f"Invoice created with ID: {invoice.id}, UUID: {invoice.uuid}")
    print(f"Total amount: ${invoice.total_amount}")
    print(f"Late fee percentage: {invoice.late_fee_percentage}%")
    
    # Manually trigger update_status_based_on_payments to mark as overdue
    print("\nTriggering status update to mark invoice as overdue...")
    invoice.update_status_based_on_payments()
    
    # Refresh from database
    invoice.refresh_from_db()
    print(f"Invoice status after update: {invoice.status}")
    print(f"Late fee applied: {invoice.late_fee_applied}")
    
    # Check if late fee was applied
    if invoice.status == 'OVERDUE' and invoice.late_fee_applied:
        print(f"Late fee amount: ${invoice.late_fee_amount}")
        
        # Check if a late fee item was created
        late_fee_item = invoice.items.filter(product="Late Payment Fee").first()
        if late_fee_item:
            print(f"Late fee item created: ${late_fee_item.amount}")
            result = True
        else:
            print("No late fee item was created")
            result = False
    else:
        print("Late fee was not applied")
        result = False
    
    print(f"\nTest result: {'PASSED' if result else 'FAILED'}")
    return result

if __name__ == "__main__":
    print("Testing partial payment functionality...")
    test_partial_payment_validation()
    print("\n" + "="*50 + "\n")
    test_late_fee_application() 