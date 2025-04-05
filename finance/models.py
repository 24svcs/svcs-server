from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from organization.models import Organization
from django.utils import timezone
import uuid
from phonenumber_field.modelfields import PhoneNumberField
from django_countries.fields import CountryField

class Address(models.Model):
    """
    Address model for storing client location information.
    Used by Client model as a foreign key.
    """
    street = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=50)
    zip_code = models.CharField(max_length=10) 
    country = CountryField()
    client = models.ForeignKey('Client', on_delete=models.CASCADE, related_name='addresses')
    
    def __str__(self):
        return f"{self.street}, {self.city}, {self.state} {self.zip_code}"
    

class Client(models.Model):
    """
    Client model representing customers in the system.
    Contains basic information and relationships to invoices and payments.
    """
    organization = models.ForeignKey(Organization, models.CASCADE, related_name='clients')
    name = models.CharField(max_length=200)
    email = models.EmailField(null=True, blank=True)
    phone = PhoneNumberField(unique=True)
    company_name = models.CharField(max_length=200, blank=True)
    tax_number = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    stripe_customer_id = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name
    
    
    @property
    def total_paid(self):
        """
        Calculate the total amount paid by this client across all invoices.
        Optimized to use prefetched payments if available.
        """
        # Use prefetched payments if available
        if hasattr(self, '_prefetched_objects_cache') and 'payments' in self._prefetched_objects_cache:
            return sum(payment.amount for payment in self._prefetched_objects_cache['payments'] 
                      if payment.status == 'COMPLETED')
        return sum(payment.amount for payment in self.payments.filter(status='COMPLETED'))
    
    @property
    def total_outstanding(self):
        """
        Calculate the total outstanding balance for this client across all invoices.
        Optimized to use prefetched invoices if available.
        """
        # Use prefetched invoices if available
        if hasattr(self, '_prefetched_objects_cache') and 'invoices' in self._prefetched_objects_cache:
            total_invoice_amount = sum(invoice.total_amount for invoice in self._prefetched_objects_cache['invoices'])
        else:
            total_invoice_amount = sum(invoice.total_amount for invoice in self.invoices.all())
        
        return total_invoice_amount - self.total_paid
    
    class Meta:
        ordering = ['name', 'company_name']


class Invoice(models.Model):
    """
    Invoice model representing financial documents issued to clients.
    Includes status tracking, payment linkage, and calculation properties.
    """
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PENDING', 'Pending'),
        ('PAID', 'Paid'),
        ('OVERDUE', 'Overdue'),
        ('CANCELLED', 'Cancelled'),
        ('PARTIALLY_PAID', 'Partially Paid'),
    ]
    
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    organization = models.ForeignKey(Organization, models.CASCADE, related_name='invoices')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='invoices')
    invoice_number = models.CharField(max_length=50, unique=True)
    issue_date = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.client.name}"
    
    @property
    def tax_amount(self):
        """Calculate the tax amount for this invoice based on item totals and tax rate."""
        # Using prefetched items if available
        if hasattr(self, '_prefetched_objects_cache') and 'items' in self._prefetched_objects_cache:
            items_total = sum(item.amount for item in self._prefetched_objects_cache['items'])
        else:
            items_total = sum(item.amount for item in self.items.all())
        return items_total * self.tax_rate / 100
    
    @property
    def total_amount(self):
        """Calculate the total invoice amount including tax."""
        # Using prefetched items if available
        if hasattr(self, '_prefetched_objects_cache') and 'items' in self._prefetched_objects_cache:
            items_total = sum(item.amount for item in self._prefetched_objects_cache['items'])
        else:
            items_total = sum(item.amount for item in self.items.all())
        return items_total + (items_total * self.tax_rate / 100)
    
    @property
    def paid_amount(self):
        """Calculate the amount paid toward this invoice so far."""
        # Use prefetched payments if available
        if hasattr(self, '_prefetched_objects_cache') and 'payments' in self._prefetched_objects_cache:
            return sum(payment.amount for payment in self._prefetched_objects_cache['payments'] 
                      if payment.status == 'COMPLETED')
        return sum(payment.amount for payment in self.payments.filter(status='COMPLETED'))
    
    @property
    def due_balance(self):
        """Calculate the remaining balance due on this invoice."""
        return self.total_amount - self.paid_amount
    
    @property
    def days_overdue(self):
        """Calculate the number of days this invoice is overdue, if applicable."""
        if self.status == 'OVERDUE':
            return (timezone.now().date() - self.due_date).days
        return 0
    
    @property
    def pending_payments(self):
        """Calculate the sum of pending payments for this invoice."""
        # Use prefetched payments if available
        if hasattr(self, '_prefetched_objects_cache') and 'payments' in self._prefetched_objects_cache:
            return sum(payment.amount for payment in self._prefetched_objects_cache['payments'] 
                      if payment.status == 'PENDING')
        return sum(payment.amount for payment in self.payments.filter(status='PENDING'))
    
    def update_status_based_on_payments(self):
        """
        Update the invoice status based on payment status and due date.
        Called automatically when payments are created, updated, or deleted.
        """
        # Don't change status for DRAFT or CANCELLED invoices
        if self.status in ['DRAFT', 'CANCELLED']:
            return
            
        # Calculate totals
        total_amount = self.total_amount
        total_paid = self.paid_amount

        if total_paid >= total_amount:
            self.status = 'PAID'
        elif total_paid > 0:
            self.status = 'PARTIALLY_PAID'
        elif self.due_date < timezone.now().date():
            self.status = 'OVERDUE'
        else:
            self.status = 'PENDING'
            
        self.save(update_fields=['status'])
    
    

class InvoiceItem(models.Model):
    """
    Line item within an invoice representing a product or service.
    Contains quantity, pricing, and description information.
    """
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    product = models.CharField(max_length=255)
    description = models.CharField(max_length=1000)  # Increased from 255
    quantity = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    unit_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.00'))]
    )

    def __str__(self):
        return f"{self.product} - {self.invoice.invoice_number}"
    
    @property
    def amount(self):
        """Calculate the line item total (quantity * unit_price)."""
        return self.quantity * self.unit_price

class Payment(models.Model):
    """
    Payment record associated with an invoice and client.
    Tracks payment status, method, and related transaction details.
    """
    PAYMENT_METHOD_CHOICES = [
        ('CASH', 'Cash'),
        ('BANK_TRANSFER', 'Bank Transfer'),
        ('CREDIT_CARD', 'Credit Card'),
        ('OTHER', 'Other'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded'),
    ]

    organization = models.ForeignKey(Organization, models.CASCADE, related_name='payments')
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='payments')
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='PENDING')
    transaction_id = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment {self.id} for Invoice {self.invoice.invoice_number}"
    
    def save(self, *args, **kwargs):
        """Override save to trigger invoice status update."""
        super().save(*args, **kwargs)
        self.invoice.update_status_based_on_payments()

class RecurringInvoice(models.Model):
    """
    Model for recurring invoice templates that automatically generate
    new invoices at specified intervals.
    """
    FREQUENCY_CHOICES = [
        ('WEEKLY', 'Weekly'),
        ('BIWEEKLY', 'Bi-Weekly'),
        ('MONTHLY', 'Monthly'),
        ('QUARTERLY', 'Quarterly'), 
        ('YEARLY', 'Yearly'),
    ]
    
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('PAUSED', 'Paused'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    organization = models.ForeignKey(Organization, models.CASCADE, related_name='recurring_invoices')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='recurring_invoices')
    title = models.CharField(max_length=255)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    notes = models.TextField(blank=True)
    next_generation_date = models.DateField()
    payment_due_days = models.PositiveIntegerField(default=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.client.name} ({self.frequency})"
    
    def calculate_next_generation_date(self):
        """Calculate the next date when an invoice should be generated."""
        from datetime import timedelta
        from dateutil.relativedelta import relativedelta
        
        if not self.next_generation_date:
            self.next_generation_date = self.start_date
            return
        
        current_date = self.next_generation_date
        
        if self.frequency == 'WEEKLY':
            next_date = current_date + timedelta(days=7)
        elif self.frequency == 'BIWEEKLY':
            next_date = current_date + timedelta(days=14)
        elif self.frequency == 'MONTHLY':
            next_date = current_date + relativedelta(months=1)
        elif self.frequency == 'QUARTERLY':
            next_date = current_date + relativedelta(months=3)
        elif self.frequency == 'YEARLY':
            next_date = current_date + relativedelta(years=1)
        else:
            next_date = current_date + relativedelta(months=1)  # Default to monthly
        
        # If end_date is set and next_date exceeds it, mark as completed
        if self.end_date and next_date > self.end_date:
            self.status = 'COMPLETED'
            self.save(update_fields=['status'])
            return
        
        self.next_generation_date = next_date
        self.save(update_fields=['next_generation_date'])
        
        return next_date
    
    def is_due_for_generation(self):
        """Check if it's time to generate a new invoice."""
        today = timezone.now().date()
        return (self.status == 'ACTIVE' and 
                self.next_generation_date <= today and 
                (not self.end_date or self.end_date >= today))

class RecurringInvoiceItem(models.Model):
    """
    Template items for recurring invoices.
    These are used as templates when generating actual invoice items.
    """
    recurring_invoice = models.ForeignKey(RecurringInvoice, on_delete=models.CASCADE, related_name='items')
    product = models.CharField(max_length=255)
    description = models.CharField(max_length=1000)
    quantity = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    unit_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.00'))]
    )

    def __str__(self):
        return f"{self.product} - {self.recurring_invoice.title}"
    
    @property
    def amount(self):
        """Calculate the line item total (quantity * unit_price)."""
        return self.quantity * self.unit_price
