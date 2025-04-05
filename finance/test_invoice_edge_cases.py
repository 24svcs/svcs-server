#!/usr/bin/env python
"""
Test invoice creation and payment processing with edge cases
This test covers various edge cases in invoice creation and payment processing
"""
import os
import sys
import django
import uuid
from decimal import Decimal
from datetime import timedelta

# Add the project path to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'svcs.settings.dev')

try:
    django.setup()
except ModuleNotFoundError as e:
    print(f"Error: {e}")
    print("\nTry running this script from the project root directory with:")
    print("python finance/test_invoice_edge_cases.py")
    sys.exit(1)

# Import Django models
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from finance.models import Organization, Client, Invoice, InvoiceItem, Payment
from finance.serializers import CreatePaymentSerializer
from core.models import User

def setup_test_data():
    """Create test organization and client if they don't exist"""
    # Get or create organization
    try:
        org = Organization.objects.first()
        if not org:
            # Create a test user if none exists
            user, _ = User.objects.get_or_create(
                email="test@example.com",
                defaults={
                    "first_name": "Test",
                    "last_name": "User"
                }
            )
            
            # Create an organization
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
    
    # Get or create client
    client, created = Client.objects.get_or_create(
        organization=org,
        name="Elon Musk",
        defaults={
            "phone": "+1987654321",
            "email": "elon@example.com",
            "company_name": "Test Company",
        }
    )
    
    return org, client

def create_invoice(org, client, **kwargs):
    """Create a test invoice with specified parameters"""
    # Generate a random invoice number
    invoice_number = kwargs.get('invoice_number', 
                               f"INV-TEST-{uuid.uuid4().hex[:6].upper()}")
    
    # Get dates
    today = timezone.now().date()
    due_date = kwargs.get('due_date', today + timedelta(days=30))
    
    # Create invoice
    invoice = Invoice.objects.create(
        organization=org,
        client=client,
        invoice_number=invoice_number,
        issue_date=kwargs.get('issue_date', today),
        due_date=due_date,
        status=kwargs.get('status', 'PENDING'),
        tax_rate=kwargs.get('tax_rate', Decimal('10.00')),
        allow_partial_payments=kwargs.get('allow_partial_payments', True),
        minimum_payment_amount=kwargs.get('minimum_payment_amount', Decimal('25.00')),
        late_fee_percentage=kwargs.get('late_fee_percentage', Decimal('5.00'))
    )
    
    # Add invoice items
    items = kwargs.get('items', [
        {
            'product': "Test Product",
            'description': "Test product description",
            'quantity': Decimal('1.00'),
            'unit_price': Decimal('100.00')
        }
    ])
    
    for item in items:
        InvoiceItem.objects.create(
            invoice=invoice,
            product=item['product'],
            description=item['description'],
            quantity=item['quantity'],
            unit_price=item['unit_price']
        )
    
    return invoice

def create_payment(invoice, **kwargs):
    """Create a payment for the invoice"""
    payment = Payment.objects.create(
        organization=invoice.organization,
        client=invoice.client,
        invoice=invoice,
        amount=kwargs.get('amount', Decimal('50.00')),
        payment_date=kwargs.get('payment_date', timezone.now().date()),
        payment_method=kwargs.get('payment_method', 'CASH'),
        status=kwargs.get('status', 'PENDING'),
        notes=kwargs.get('notes', "Test payment")
    )
    return payment

def test_invoice_edge_cases():
    """Test invoice creation with edge cases"""
    print("=== Testing Invoice Creation Edge Cases ===")
    
    org, client = setup_test_data()
    results = {}
    
    # Test 1: Invoice with zero tax rate
    try:
        invoice = create_invoice(org, client, tax_rate=Decimal('0.00'))
        print(f"Created invoice with zero tax rate: {invoice.invoice_number}")
        print(f"  Total amount: ${invoice.total_amount}")
        print(f"  Tax amount: ${invoice.tax_amount}")
        results["Zero tax rate"] = "PASSED"
    except Exception as e:
        print(f"Error creating invoice with zero tax rate: {e}")
        results["Zero tax rate"] = "FAILED"
    
    # Test 2: Invoice with future issue date
    try:
        future_date = timezone.now().date() + timedelta(days=10)
        invoice = create_invoice(org, client, issue_date=future_date)
        print(f"Created invoice with future issue date: {invoice.invoice_number}")
        print(f"  Issue date: {invoice.issue_date}")
        print(f"  Due date: {invoice.due_date}")
        results["Future issue date"] = "PASSED"
    except Exception as e:
        print(f"Error creating invoice with future issue date: {e}")
        results["Future issue date"] = "FAILED"
    
    # Test 3: Invoice with due date before issue date (should raise error)
    try:
        today = timezone.now().date()
        past_date = today - timedelta(days=5)
        invoice = create_invoice(org, client, issue_date=today, due_date=past_date)
        print("Created invoice with due date before issue date - NO ERROR WAS RAISED")
        results["Due date before issue date"] = "FAILED (No validation error)"
    except ValidationError as e:
        print(f"Validation error for due date before issue date: {e}")
        results["Due date before issue date"] = "PASSED (Validation caught)"
    except Exception as e:
        print(f"Error creating invoice with due date before issue date: {e}")
        results["Due date before issue date"] = "FAILED"
    
    # Test 4: Invoice with multiple items including zero-price item
    try:
        items = [
            {
                'product': "Regular Product",
                'description': "Regular product with normal price",
                'quantity': Decimal('1.00'),
                'unit_price': Decimal('100.00')
            },
            {
                'product': "Free Item",
                'description': "Free promotional item",
                'quantity': Decimal('1.00'),
                'unit_price': Decimal('0.00')
            }
        ]
        invoice = create_invoice(org, client, items=items)
        print(f"Created invoice with zero-price item: {invoice.invoice_number}")
        print(f"  Total amount: ${invoice.total_amount}")
        print(f"  Number of items: {invoice.items.count()}")
        results["Zero-price item"] = "PASSED"
    except Exception as e:
        print(f"Error creating invoice with zero-price item: {e}")
        results["Zero-price item"] = "FAILED"
    
    # Test 5: Invoice with fractional quantities
    try:
        items = [
            {
                'product': "Hourly Service",
                'description': "Consulting service billed by hour",
                'quantity': Decimal('2.50'),
                'unit_price': Decimal('85.00')
            }
        ]
        invoice = create_invoice(org, client, items=items)
        print(f"Created invoice with fractional quantity: {invoice.invoice_number}")
        print(f"  Quantity: {invoice.items.first().quantity}")
        print(f"  Item amount: ${invoice.items.first().amount}")
        print(f"  Total amount: ${invoice.total_amount}")
        results["Fractional quantity"] = "PASSED"
    except Exception as e:
        print(f"Error creating invoice with fractional quantity: {e}")
        results["Fractional quantity"] = "FAILED"
    
    # Test 6: Invoice with partial payments disallowed but minimum amount set
    try:
        invoice = create_invoice(
            org, client, 
            allow_partial_payments=False,
            minimum_payment_amount=Decimal('50.00')
        )
        print("Created invoice with partial payments disabled but minimum amount set - NO ERROR WAS RAISED")
        results["Inconsistent partial payment settings"] = "FAILED (No validation error)"
    except ValidationError as e:
        print(f"Validation error for inconsistent partial payment settings: {e}")
        results["Inconsistent partial payment settings"] = "PASSED (Validation caught)"
    except Exception as e:
        print(f"Error: {e}")
        results["Inconsistent partial payment settings"] = "FAILED"
    
    # Print summary of invoice creation tests
    print("\n=== Invoice Creation Test Results ===")
    for test, result in results.items():
        print(f"{test}: {result}")
    
    return results

def test_payment_edge_cases():
    """Test payment processing with edge cases"""
    print("\n=== Testing Payment Processing Edge Cases ===")
    
    org, client = setup_test_data()
    results = {}
    
    # Create a base invoice for payment tests
    invoice = create_invoice(org, client)
    print(f"Created base invoice for payment tests: {invoice.invoice_number}")
    print(f"  Total amount: ${invoice.total_amount}")
    print(f"  Status: {invoice.status}")
    
    # Test 1: Payment exceeding invoice amount
    try:
        payment = create_payment(invoice, amount=invoice.total_amount + Decimal('20.00'))
        print(f"Created payment exceeding invoice amount: ${payment.amount}")
        print(f"  Payment status: {payment.status}")
        print(f"  Invoice status after payment: {invoice.status}")
        results["Payment exceeding invoice"] = "PASSED"
    except Exception as e:
        print(f"Error creating payment exceeding invoice amount: {e}")
        results["Payment exceeding invoice"] = "FAILED"
    
    # Test 2: Multiple payments adding up to invoice amount
    invoice = create_invoice(org, client)
    try:
        half_amount = (invoice.total_amount / 2).quantize(Decimal('0.01'))
        payment1 = create_payment(invoice, amount=half_amount)
        print(f"Created first half payment: ${payment1.amount}")
        
        payment2 = create_payment(invoice, amount=half_amount)
        print(f"Created second half payment: ${payment2.amount}")
        
        print(f"  Invoice status after payments: {invoice.status}")
        print(f"  Total paid: ${invoice.paid_amount}")
        results["Multiple payments"] = "PASSED"
    except Exception as e:
        print(f"Error creating multiple payments: {e}")
        results["Multiple payments"] = "FAILED"
    
    # Test 3: Payment with zero amount (should fail validation)
    invoice = create_invoice(org, client)
    try:
        payment = create_payment(invoice, amount=Decimal('0.00'))
        print("Created payment with zero amount - NO ERROR WAS RAISED")
        results["Zero amount payment"] = "FAILED (No validation error)"
    except ValidationError as e:
        print(f"Validation error for zero amount payment: {e}")
        results["Zero amount payment"] = "PASSED (Validation caught)"
    except Exception as e:
        print(f"Error creating payment with zero amount: {e}")
        results["Zero amount payment"] = "FAILED"
    
    # Test 4: Payment for fully paid invoice
    try:
        invoice = create_invoice(org, client)
        payment = create_payment(invoice, amount=invoice.total_amount)
        print(f"Created full payment: ${payment.amount}")
        print(f"  Invoice status after payment: {invoice.status}")
        
        # Try to create another payment
        try:
            payment2 = create_payment(invoice, amount=Decimal('10.00'))
            print("Created payment for fully paid invoice - THIS SHOULD NOT HAPPEN")
            results["Payment for paid invoice"] = "FAILED (Payment allowed)"
        except ValidationError as e:
            print(f"Validation error for payment on paid invoice: {e}")
            results["Payment for paid invoice"] = "PASSED (Validation caught)"
        except Exception as e:
            print(f"Other error: {e}")
            results["Payment for paid invoice"] = "FAILED"
            
    except Exception as e:
        print(f"Error in test setup: {e}")
        results["Payment for paid invoice"] = "FAILED"
    
    # Test 5: Payment for overdue invoice
    try:
        past_date = timezone.now().date() - timedelta(days=10)
        invoice = create_invoice(
            org, client, 
            issue_date=past_date,
            due_date=past_date + timedelta(days=5),
            late_fee_percentage=Decimal('10.00')
        )
        
        # Force status update to make it overdue
        invoice.update_status_based_on_payments()
        print(f"Created overdue invoice: {invoice.invoice_number}")
        print(f"  Status: {invoice.status}")
        print(f"  Late fee amount: ${invoice.late_fee_amount}")
        
        # Create payment
        payment = create_payment(invoice, amount=invoice.total_amount)
        print(f"Created payment for overdue invoice: ${payment.amount}")
        print(f"  Invoice status after payment: {invoice.status}")
        results["Payment for overdue invoice"] = "PASSED"
    except Exception as e:
        print(f"Error creating payment for overdue invoice: {e}")
        results["Payment for overdue invoice"] = "FAILED"
    
    # Print summary of payment tests
    print("\n=== Payment Processing Test Results ===")
    for test, result in results.items():
        print(f"{test}: {result}")
    
    return results

def run_all_tests():
    """Run all tests"""
    print("Testing invoice edge cases and payment processing...\n")
    
    invoice_results = test_invoice_edge_cases()
    payment_results = test_payment_edge_cases()
    
    # Check if each test actually passed (the PASSED result may include "PASSED (Validation caught)")
    invoice_passed = all("PASSED" in result for result in invoice_results.values())
    payment_passed = all("PASSED" in result for result in payment_results.values())
    all_passed = invoice_passed and payment_passed
    
    print("\n=== Overall Test Result ===")
    print(f"Invoice tests: {'PASSED' if invoice_passed else 'FAILED'}")
    print(f"Payment tests: {'PASSED' if payment_passed else 'FAILED'}")
    print(f"Overall result: {'PASSED' if all_passed else 'FAILED'}")

if __name__ == "__main__":
    run_all_tests() 