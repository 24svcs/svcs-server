#!/usr/bin/env python
"""
Test the payment workflow directly
"""
import os
import sys
import django

# Add the project directory to the Python path
# This ensures the script can find modules regardless of where it's run from
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'svcs.settings.dev')

try:
    django.setup()
except ModuleNotFoundError as e:
    print(f"Error: {e}")
    print("\nTry running this script from the project root directory with:")
    print("python test_payment_workflow.py")
    sys.exit(1)

from decimal import Decimal
import uuid
from django.utils import timezone
from finance.models import Client, Invoice, Payment, Organization, InvoiceItem
from django.db import transaction
from datetime import timedelta

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
        
        # Add an invoice item
        InvoiceItem.objects.create(
            invoice=invoice,
            product="Test Product",
            description="Test product for payment testing",
            quantity=Decimal('1.00'),
            unit_price=Decimal('100.00')
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

def test_invoice_status_updates():
    """Test that invoice status is updated correctly based on payments."""
    print("\n=== Testing Invoice Status Updates ===")
    
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
    
    # Test cases for regular payments and status transitions
    # Create a test invoice for payment status tests
    invoice_number = f"INV-TEST-STATUS-{uuid.uuid4().hex[:6].upper()}"
    today = timezone.now().date()
    
    print(f"Creating invoice {invoice_number} for client {client.name}")
    
    invoice = Invoice.objects.create(
        organization=org,
        client=client,
        invoice_number=invoice_number,
        issue_date=today,
        due_date=today + timezone.timedelta(days=30),
        status='DRAFT',
        tax_rate=Decimal('10.00')
    )
    
    # Add an invoice item
    item = InvoiceItem.objects.create(
        invoice=invoice,
        product="Test Product",
        description="Test product for status update testing",
        quantity=Decimal('1.00'),
        unit_price=Decimal('100.00')
    )
    
    invoice_total = invoice.total_amount
    print(f"Invoice created with total: ${invoice_total}")
    
    # Test cases for invoice status changes
    test_cases = [
        {
            "name": "DRAFT -> PENDING",
            "initial_status": "DRAFT",
            "payment_amount": None,  # No payment, just change status
            "target_status": "PENDING",
            "check_func": lambda inv: inv.status == "PENDING"
        },
        {
            "name": "PENDING -> PARTIALLY_PAID",
            "initial_status": "PENDING",
            "payment_amount": invoice_total / 2,  # Half payment
            "target_status": "PARTIALLY_PAID",
            "check_func": lambda inv: inv.status == "PARTIALLY_PAID"
        },
        {
            "name": "PARTIALLY_PAID -> PAID",
            "initial_status": "PARTIALLY_PAID",
            "payment_amount": invoice_total / 2,  # Remaining half
            "target_status": "PAID",
            "check_func": lambda inv: inv.status == "PAID"
        }
    ]
    
    results = {}
    
    for case in test_cases:
        print(f"\nTesting: {case['name']}")
        
        # Set initial status
        invoice.status = case['initial_status']
        invoice.save()
        print(f"  Set status to: {invoice.status}")
        
        if case.get('special') == 'make_overdue':
            # Make the invoice overdue by setting due_date in the past
            past_date = today - timezone.timedelta(days=1)
            invoice.due_date = past_date
            invoice.save()
            print(f"  Set due date to past: {invoice.due_date}")
            
            # Trigger status update
            invoice.update_status_based_on_payments()
        elif case['payment_amount'] is not None:
            # Create a payment
            with transaction.atomic():
                payment = Payment.objects.create(
                    organization=org,
                    client=client,
                    invoice=invoice,
                    amount=case['payment_amount'],
                    payment_date=today,
                    payment_method='CASH',  # Auto-completes
                    notes=f"Test payment for {case['name']}"
                )
                print(f"  Created payment: ${case['payment_amount']}")
        else:
            # Just update the status manually
            invoice.status = case['target_status']
            invoice.save()
        
        # Refresh from database
        invoice.refresh_from_db()
        print(f"  Resulting status: {invoice.status}")
        
        # Check if status is as expected
        passed = case['check_func'](invoice)
        results[case['name']] = passed
        print(f"  Result: {'PASSED' if passed else 'FAILED'}")
        
    # Test 4: PENDING -> OVERDUE (past due date)
    print("\nCreating a separate invoice for overdue testing...")
    print("Testing: PENDING -> OVERDUE (past due date)")
    
    # Create a fresh invoice specifically for testing overdue transition
    overdue_invoice = Invoice.objects.create(
        organization=org,
        client=client,
        invoice_number=f"INV-TEST-OVERDUE-{uuid.uuid4().hex[:6].upper()}",
        issue_date=timezone.now().date() - timedelta(days=10),  # 10 days ago
        due_date=timezone.now().date() - timedelta(days=1),     # Yesterday (past due)
        status='PENDING',
        tax_rate=Decimal('10.00')
    )
    
    # Add an invoice item
    InvoiceItem.objects.create(
        invoice=overdue_invoice,
        product="Test Product",
        description="Test product for payment testing",
        quantity=Decimal('1.00'),
        unit_price=Decimal('100.00')
    )
    
    print(f"  Starting with fresh invoice: {overdue_invoice.invoice_number}")
    print(f"  Initial status: {overdue_invoice.status}")
    print(f"  Set due date to past: {overdue_invoice.due_date}")
    
    # Force status update to check for overdue
    overdue_invoice.update_status_based_on_payments()
    
    # Refresh from database
    overdue_invoice.refresh_from_db()
    print(f"  Resulting status: {overdue_invoice.status}")
    
    # Check if status is as expected
    overdue_result = overdue_invoice.status == "OVERDUE"
    results["PENDING -> OVERDUE (past due date)"] = overdue_result
    print(f"  Result: {'PASSED' if overdue_result else 'FAILED'}")
    
    # Print summary
    print("\n=== Status Update Test Results ===")
    all_passed = True
    for test, passed in results.items():
        print(f"{test}: {'PASSED' if passed else 'FAILED'}")
        if not passed:
            all_passed = False
    
    print(f"\nOverall result: {'PASSED' if all_passed else 'FAILED'}")
    return all_passed

if __name__ == "__main__":
    print("Testing payment workflow...")
    test_non_credit_card_payment_auto_completion()
    print("\n" + "="*50 + "\n")
    test_invoice_status_updates() 