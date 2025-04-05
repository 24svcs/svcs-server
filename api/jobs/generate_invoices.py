from celery import shared_task
from django.db import transaction
from finance.models import RecurringInvoice, Invoice, InvoiceItem
from django.utils import timezone
from datetime import timedelta
import uuid
import logging

logger = logging.getLogger(__name__)

@shared_task
def generate_recurring_invoices():
    """
    Celery task to generate invoices from active recurring templates
    that are due for generation.
    """
    today = timezone.now().date()
    logger.info(f"Starting recurring invoice generation for {today}")
    
    # Find all active recurring invoices due for generation
    recurring_invoices = RecurringInvoice.objects.filter(
        status='ACTIVE',
        next_generation_date__lte=today
    )
    
    total_generated = 0
    
    for recurring_invoice in recurring_invoices:
        logger.info(f"Processing recurring invoice: {recurring_invoice.title} (ID: {recurring_invoice.id})")
        
        try:
            with transaction.atomic():
                # Generate invoice
                invoice = create_invoice_from_template(recurring_invoice)
                logger.info(f"Generated invoice {invoice.invoice_number} from recurring template")
                
                # Update next generation date
                recurring_invoice.calculate_next_generation_date()
                logger.info(f"Updated next generation date to {recurring_invoice.next_generation_date}")
                
                total_generated += 1
                
        except Exception as e:
            logger.error(f"Error generating invoice from recurring template {recurring_invoice.id}: {str(e)}")
    
    logger.info(f"Completed recurring invoice generation. Generated {total_generated} invoices.")
    return total_generated

def create_invoice_from_template(recurring_invoice):
    """
    Create a new invoice from a recurring invoice template.
    """
    # Calculate dates
    today = timezone.now().date()
    due_date = today + timedelta(days=recurring_invoice.payment_due_days)
    
    # Generate a unique invoice number
    random_suffix = str(uuid.uuid4().hex)[:6].upper()
    invoice_number = f"INV-{random_suffix}"
    while Invoice.objects.filter(invoice_number=invoice_number).exists():
        random_suffix = str(uuid.uuid4().hex)[:6].upper()
        invoice_number = f"INV-{random_suffix}"
    
    # Create the invoice
    invoice = Invoice.objects.create(
        organization_id=recurring_invoice.organization_id,
        client=recurring_invoice.client,
        invoice_number=invoice_number,
        issue_date=today,
        due_date=due_date,
        status='DRAFT',
        tax_rate=recurring_invoice.tax_rate,
        notes=f"Generated from recurring template: {recurring_invoice.title}\n\n{recurring_invoice.notes}".strip()
    )
    
    # Create all invoice items from the template
    for template_item in recurring_invoice.items.all():
        InvoiceItem.objects.create(
            invoice=invoice,
            product=template_item.product,
            description=template_item.description,
            quantity=template_item.quantity,
            unit_price=template_item.unit_price
        )
    
    return invoice 