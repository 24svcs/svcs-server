#!/usr/bin/env python
"""
Test script for the public invoice payment endpoint.
This script finds an invoice that can be paid and generates a link to pay it.

Usage: python test_public_payment.py
"""
import os
import sys
import django
import webbrowser

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'svcs.settings.dev')
django.setup()

# Now import Django models
from finance.models import Invoice

def find_payable_invoice():
    """Find an invoice that can be paid"""
    invoice = Invoice.objects.filter(
        status__in=['PENDING', 'OVERDUE', 'PARTIALLY_PAID']
    ).first()
    
    if not invoice:
        print("No payable invoices found")
        return None
    
    return invoice

def get_public_payment_url(invoice, base_url="http://localhost:8000"):
    """Generate the public payment URL for an invoice"""
    return f"{base_url}/pay-invoice/{invoice.uuid}/"

def main():
    """Main function"""
    print("=== Public Invoice Payment Test ===")
    
    # Find a payable invoice
    invoice = find_payable_invoice()
    if not invoice:
        print("No payable invoices found. Please create an invoice with status PENDING, OVERDUE, or PARTIALLY_PAID.")
        return 1
    
    # Print invoice details
    print(f"Found payable invoice: #{invoice.invoice_number}")
    print(f"Amount due: ${invoice.due_balance}")
    print(f"Status: {invoice.status}")
    print(f"Client: {invoice.client.name}")
    
    # Generate payment URL
    payment_url = get_public_payment_url(invoice)
    print("\nPayment URL:")
    print(payment_url)
    
    # Ask if user wants to open the URL
    print("\nThis URL can be shared with anyone to allow them to pay this invoice.")
    print("No authentication is required to access this page.")
    
    choice = input("\nDo you want to open this URL in your browser? (y/n): ")
    if choice.lower() == 'y':
        webbrowser.open(payment_url)
        print("URL opened in browser.")
    
    # Show curl command for testing API directly
    print("\nTo test the API directly, you can use these curl commands:")
    print(f"\n# Get invoice details:")
    print(f"curl -X GET {payment_url}")
    
    print(f"\n# Create payment intent:")
    print(f'curl -X POST {payment_url} -H "Content-Type: application/json" -d \'{{"return_url": "http://localhost:8000"}}\'')
    
    print("\nTest completed!")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 