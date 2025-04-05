#!/usr/bin/env python
"""
Test the payment workflow directly
"""
import os
import sys
import django

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'svcs.settings.prod')
django.setup()

from decimal import Decimal
import uuid
from django.utils import timezone
from finance.models import Client, Invoice, Payment, Organization
from django.db import transaction

def test_non_credit_card_payment_auto_completion():
    """Test that non-credit card payments are automatically marked as COMPLETED."""
    
    # Find an organization
    org = Organization.objects.first()
    if not org:
        print("No organization found. Test failed.")
        return False
    
    # Find a client
    client = Client.objects.filter(organization=org).first()
    if not client:
        print("No client found. Test failed.")
        return False
    
    # Find or create an invoice
    invoice = Invoice.objects.filter(client=client, status='PENDING').first()
    if not invoice:
        print("Creating a new test invoice...")
        # Create a test invoice
        invoice_number = f"INV-TEST-{uuid.uuid4().hex[:6].upper()}"
        invoice = Invoice.objects.create(
            organization=org,
            client=client,
            invoice_number=invoice_number,
            issue_date=timezone.now().date(),
            due_date=timezone.now().date() + timezone.timedelta(days=30),
            status='PENDING',
            tax_rate=Decimal('10.00')
        )
    
    # Test each non-credit card payment method
    payment_methods = ['CASH', 'BANK_TRANSFER', 'OTHER']
    results = {}
    
    for method in payment_methods:
        print(f"\nTesting {method} payment:")
        with transaction.atomic():
            # Create a payment
            payment = Payment.objects.create(
                organization=org,
                client=client,
                invoice=invoice,
                amount=Decimal('10.00'),
                payment_date=timezone.now().date(),
                payment_method=method,
                notes=f"Test {method} payment - should be auto-completed"
            )
            
            print(f"  Created payment ID: {payment.id}")
            print(f"  Initial status: {payment.status}")
            
            # Verify it was automatically set to COMPLETED
            payment.refresh_from_db()
            result = payment.status == 'COMPLETED'
            results[method] = result
            
            print(f"  Final status: {payment.status}")
            print(f"  Test result: {'PASSED' if result else 'FAILED'}")
    
    # Test credit card payment - should stay PENDING
    print("\nTesting CREDIT_CARD payment:")
    with transaction.atomic():
        payment = Payment.objects.create(
            organization=org,
            client=client,
            invoice=invoice,
            amount=Decimal('10.00'),
            payment_date=timezone.now().date(),
            payment_method='CREDIT_CARD',
            transaction_id=f"pi_test_{uuid.uuid4().hex[:24]}",
            notes="Test CREDIT_CARD payment - should stay PENDING"
        )
        
        print(f"  Created payment ID: {payment.id}")
        print(f"  Initial status: {payment.status}")
        
        # Verify it stays PENDING
        payment.refresh_from_db()
        result = payment.status == 'PENDING'
        results['CREDIT_CARD'] = result
        
        print(f"  Final status: {payment.status}")
        print(f"  Test result: {'PASSED' if result else 'FAILED'}")
    
    # Print summary
    print("\n=== Test Results ===")
    all_passed = True
    for method, passed in results.items():
        print(f"{method}: {'PASSED' if passed else 'FAILED'}")
        if not passed:
            all_passed = False
    
    print(f"\nOverall result: {'PASSED' if all_passed else 'FAILED'}")
    return all_passed

if __name__ == "__main__":
    print("Testing payment workflow...")
    test_non_credit_card_payment_auto_completion() 