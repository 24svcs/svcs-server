from celery import shared_task
from django.utils import timezone
from django.db import transaction
from .models import Invoice
import logging

logger = logging.getLogger(__name__)

@shared_task
def process_overdue_invoices():
    """
    Process all overdue invoices:
    1. Change status to OVERDUE for past due invoices in non-final statuses
    2. Apply late fees for overdue invoices that haven't had fees applied yet
    """
    today = timezone.now().date()
    
    # Find invoices that are past due but not marked as overdue yet
    # Check all non-final statuses: SENT, PARTIALLY_PAID
    pending_overdue_invoices = Invoice.objects.filter(
        status__in=['SENT', 'PARTIALLY_PAID'],
        due_date__lt=today
    )
    
    logger.info(f"Found {pending_overdue_invoices.count()} pending invoices that are past due")
    
    overdue_count = 0
    late_fees_count = 0
    
    # Process each invoice
    for invoice in pending_overdue_invoices:
        try:
            with transaction.atomic():
                # Let update_status_based_on_payments handle the status update
                old_status = invoice.status
                invoice.update_status_based_on_payments()
                
                if invoice.status == 'OVERDUE' and old_status != 'OVERDUE':
                    logger.info(f"Changed invoice {invoice.invoice_number} status from {old_status} to OVERDUE")
                    overdue_count += 1
                
                # Apply late fee if configured
                if invoice.late_fee_percentage > 0 and not invoice.late_fee_applied:
                    if invoice.apply_late_fee():
                        logger.info(f"Applied late fee of {invoice.late_fee_amount} to invoice {invoice.invoice_number}")
                        late_fees_count += 1
        except Exception as e:
            logger.error(f"Error processing invoice {invoice.invoice_number}: {str(e)}")
    
    # Find already overdue invoices that need late fees
    overdue_invoices = Invoice.objects.filter(
        status='OVERDUE',
        late_fee_applied=False,
        late_fee_percentage__gt=0
    )
    
    logger.info(f"Found {overdue_invoices.count()} overdue invoices that need late fees")
    
    # Apply late fees to overdue invoices
    for invoice in overdue_invoices:
        try:
            with transaction.atomic():
                if invoice.apply_late_fee():
                    logger.info(f"Applied late fee of {invoice.late_fee_amount} to invoice {invoice.invoice_number}")
                    late_fees_count += 1
        except Exception as e:
            logger.error(f"Error applying late fee to invoice {invoice.invoice_number}: {str(e)}")
    
    return {
        'overdue_count': overdue_count,
        'late_fees_count': late_fees_count
    }

@shared_task
def send_payment_reminders():
    """
    Send payment reminders for eligible invoices:
    - Pending invoices approaching due date
    - Overdue invoices that haven't received too many reminders
    """
    today = timezone.now().date()
    
    # Find invoices due in the next 3 days
    upcoming_due_invoices = Invoice.objects.filter(
        status='PENDING',
        due_date__range=[today, today + timezone.timedelta(days=3)],
        payment_reminders_sent__lt=3
    ).exclude(
        last_reminder_date__gte=today - timezone.timedelta(days=7)  # No reminders in the last week
    )
    
    logger.info(f"Found {upcoming_due_invoices.count()} upcoming due invoices eligible for reminders")
    
    # Find overdue invoices
    overdue_invoices = Invoice.objects.filter(
        status__in=['OVERDUE', 'PARTIALLY_PAID'],
        payment_reminders_sent__lt=3
    ).exclude(
        last_reminder_date__gte=today - timezone.timedelta(days=7)  # No reminders in the last week
    )
    
    logger.info(f"Found {overdue_invoices.count()} overdue invoices eligible for reminders")
    
    reminders_sent = 0
    
    # Send reminders for upcoming due invoices
    for invoice in upcoming_due_invoices:
        try:
            # Here would be the actual implementation to send an email
            # For now, just update the tracking fields
            invoice.payment_reminders_sent += 1
            invoice.last_reminder_date = today
            invoice.save(update_fields=['payment_reminders_sent', 'last_reminder_date'])
            
            logger.info(f"Sent upcoming due reminder for invoice {invoice.invoice_number}")
            reminders_sent += 1
        except Exception as e:
            logger.error(f"Error sending reminder for invoice {invoice.invoice_number}: {str(e)}")
    
    # Send reminders for overdue invoices
    for invoice in overdue_invoices:
        try:
            # Here would be the actual implementation to send an email
            # For now, just update the tracking fields
            invoice.payment_reminders_sent += 1
            invoice.last_reminder_date = today
            invoice.save(update_fields=['payment_reminders_sent', 'last_reminder_date'])
            
            logger.info(f"Sent overdue reminder for invoice {invoice.invoice_number}")
            reminders_sent += 1
        except Exception as e:
            logger.error(f"Error sending reminder for invoice {invoice.invoice_number}: {str(e)}")
    
    return {
        "reminders_sent": reminders_sent
    } 