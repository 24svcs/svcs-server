#!/usr/bin/env python
"""
Create test data for payment workflow testing
"""
import os
import django
import uuid
from decimal import Decimal
from datetime import datetime, timedelta

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'svcs.settings.prod')
django.setup()

# Import Django models
from organization.models import Organization
from finance.models import Client, Invoice, InvoiceItem, Payment
from django.utils import timezone

def create_test_invoice_with_payment():
    """Create a test invoice with a pending credit card payment."""
    try:
        # Get the first organization
        org = Organization.objects.first()
        if not org:
            print("No organization found. Please create an organization first.")
            return
            
        # Get a client for this organization
        client = Client.objects.filter(organization=org).first()
        if not client:
            print("No client found. Please create a client first.")
            return
        
        # Create a new invoice
        invoice_number = f"INV-TEST-{uuid.uuid4().hex[:6].upper()}"
        today = timezone.now().date()
        due_date = today + timedelta(days=30)
        
        invoice = Invoice.objects.create(
            organization=org,
            client=client,
            invoice_number=invoice_number,
            issue_date=today,
            due_date=due_date,
            status='PENDING',
            tax_rate=Decimal('10.00')
        )
        
        # Add an invoice item
        item = InvoiceItem.objects.create(
            invoice=invoice,
            product="Test Product",
            description="Test product for payment testing",
            quantity=Decimal('1.00'),
            unit_price=Decimal('100.00')
        )
        
        # Create a test payment with a fake Stripe transaction ID
        test_transaction_id = f"pi_test_{uuid.uuid4().hex[:24]}"
        payment = Payment.objects.create(
            organization=org,
            client=client,
            invoice=invoice,
            amount=Decimal('55.00'),  # Partial payment
            payment_date=today,
            payment_method='CREDIT_CARD',
            status='PENDING',
            transaction_id=test_transaction_id,
            notes="Test payment for webhook testing"
        )
        
        print(f"Created test invoice: {invoice.invoice_number} (ID: {invoice.id}, UUID: {invoice.uuid})")
        print(f"Created test payment: ID {payment.id}, Transaction ID: {payment.transaction_id}")
        print(f"Payment status: {payment.status}")
        print(f"Amount: ${payment.amount}")
        print("\nTo test the webhook, run:")
        print(f"export STRIPE_WEBHOOK_TEST_MODE=true")
        print(f"python finance/test_webhook_local.py payment_intent.succeeded {payment.id}")
        
        return payment
    
    except Exception as e:
        print(f"Error creating test data: {str(e)}")
        return None

if __name__ == "__main__":
    print("Creating test data for payment workflow...")
    create_test_invoice_with_payment() 