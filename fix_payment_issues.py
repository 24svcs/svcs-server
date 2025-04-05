#!/usr/bin/env python
import os
import django
import sys
import logging

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'svcs.settings')
django.setup()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

from finance.models import Invoice, Payment
from decimal import Decimal

def check_specific_invoice(invoice_number):
    """Check a specific invoice for payment issues."""
    logger.info(f"Checking invoice {invoice_number}...")
    
    try:
        invoice = Invoice.objects.get(invoice_number=invoice_number)
    except Invoice.DoesNotExist:
        logger.error(f"Invoice {invoice_number} not found!")
        return
    
    # Get all payments
    all_payments = Payment.objects.filter(invoice=invoice).order_by('created_at')
    completed_payments = all_payments.filter(status='COMPLETED')
    pending_payments = all_payments.filter(status='PENDING')
    
    # Calculate totals
    invoice_total = invoice.total_amount
    payment_total = sum(payment.amount for payment in completed_payments)
    pending_total = sum(payment.amount for payment in pending_payments)
    
    logger.info(f"Invoice details:")
    logger.info(f"  - Number: {invoice.invoice_number}")
    logger.info(f"  - Client: {invoice.client.name}")
    logger.info(f"  - Total amount: ${invoice_total}")
    logger.info(f"  - Status: {invoice.status}")
    logger.info(f"  - Paid amount: ${payment_total}")
    logger.info(f"  - Pending amount: ${pending_total}")
    logger.info(f"  - Due balance: ${invoice.due_balance}")
    
    logger.info(f"Payments:")
    for payment in all_payments:
        logger.info(f"  - ID: {payment.id}, Amount: ${payment.amount}, Status: {payment.status}, Created: {payment.created_at}")
    
    # Check for overpayment
    if payment_total > invoice_total:
        logger.warning(f"This invoice has an overpayment issue:")
        logger.warning(f"  - Invoice total: ${invoice_total}")
        logger.warning(f"  - Payment total: ${payment_total}")
        logger.warning(f"  - Difference: ${payment_total - invoice_total}")
        
        # Check for possible duplicate payments
        if len(completed_payments) > 1 and payment_total >= invoice_total * 2:
            logger.error(f"Possible duplicate payment detected!")
            
            # Ask if we should fix it
            if input(f"Do you want to fix the overpayment for invoice {invoice.invoice_number}? (y/n): ").lower() == 'y':
                # Sort payments to find duplicates
                for i, payment in enumerate(completed_payments):
                    if i > 0 and payment.amount == completed_payments[i-1].amount:
                        # Likely a duplicate
                        logger.warning(f"Payment ID {payment.id} appears to be a duplicate of ID {completed_payments[i-1].id}")
                        
                        # Ask how to handle this
                        action = input("What action do you want to take? (1=mark as refunded, 2=delete, 3=adjust amount, 4=skip): ")
                        
                        if action == '1':
                            payment.status = 'REFUNDED'
                            payment.notes += "\nMarked as refunded due to duplicate payment."
                            payment.save()
                            logger.info(f"Marked payment {payment.id} as REFUNDED")
                        elif action == '2':
                            if input(f"Are you SURE you want to DELETE payment {payment.id}? This cannot be undone! (yes/no): ") == 'yes':
                                payment.delete()
                                logger.info(f"Deleted payment {payment.id}")
                        elif action == '3':
                            # Calculate the correct amount
                            remaining = invoice_total
                            for p in completed_payments:
                                if p.id != payment.id:
                                    remaining -= p.amount
                            
                            if remaining <= 0:
                                logger.warning(f"Cannot adjust amount - it would be ${remaining} which is invalid")
                                continue
                            
                            payment.amount = remaining
                            payment.notes += f"\nAdjusted amount to ${remaining} to fix overpayment."
                            payment.save()
                            logger.info(f"Adjusted payment {payment.id} amount to ${remaining}")

def check_and_fix_payment_issues():
    """Check for issues with payments and invoices and fix them."""
    logger.info("Starting payment issue diagnosis...")
    
    # First check specific invoice
    specific_invoice = input("Enter a specific invoice number to check (or press Enter to check all): ").strip()
    if specific_invoice:
        check_specific_invoice(specific_invoice)
        return
    
    # Find invoices with negative balances
    invoices_with_issues = Invoice.objects.filter(status='PAID').all()
    logger.info(f"Found {len(invoices_with_issues)} paid invoices to check")
    
    for invoice in invoices_with_issues:
        # Get all completed payments
        completed_payments = Payment.objects.filter(invoice=invoice, status='COMPLETED')
        
        # Calculate total from invoice items
        invoice_total = invoice.total_amount
        
        # Sum of completed payments
        payment_total = sum(payment.amount for payment in completed_payments)
        
        # Check for overpayment
        if payment_total > invoice_total:
            logger.warning(f"Invoice {invoice.invoice_number} has an overpayment issue:")
            logger.warning(f"  - Invoice total: ${invoice_total}")
            logger.warning(f"  - Payment total: ${payment_total}")
            logger.warning(f"  - Difference: ${payment_total - invoice_total}")
            
            # List all payments
            logger.info(f"Payments for invoice {invoice.invoice_number}:")
            for payment in completed_payments:
                logger.info(f"  - Payment ID {payment.id}: ${payment.amount} - {payment.created_at.date()} - Status: {payment.status}")
            
            # Check for duplicate or incorrect payments
            if len(completed_payments) > 1 and payment_total >= invoice_total * 2:
                logger.error(f"Possible duplicate payment detected for invoice {invoice.invoice_number}")
                
                # Ask if user wants to check this invoice in detail
                if input(f"Do you want to check this invoice in detail? (y/n): ").lower() == 'y':
                    check_specific_invoice(invoice.invoice_number)
                    
    logger.info("Diagnosis complete!")
    
if __name__ == '__main__':
    # If an argument is provided, check that specific invoice
    if len(sys.argv) > 1:
        check_specific_invoice(sys.argv[1])
    else:
        check_and_fix_payment_issues() 