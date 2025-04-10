from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from organization.models import Organization
from django.utils import timezone
import uuid
from phonenumber_field.modelfields import PhoneNumberField
from django_countries.fields import CountryField
import logging
from django.db.models import Sum
from django.core.exceptions import ValidationError

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
    name = models.CharField(max_length=200, unique=True)
    email = models.EmailField(null=True, blank=True)
    phone = PhoneNumberField(unique=True)
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
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['email']),
            models.Index(fields=['phone']),
        ]
        
    

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
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='invoices')
    invoice_number = models.CharField(max_length=50, unique=True)
    issue_date = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    late_fee_percentage = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=Decimal('0.00'), 
        help_text="Late fee percentage to apply on overdue invoices"
    )
    late_fee_applied = models.BooleanField(
        default=False,
        editable=False,
        help_text="Whether late fee has been applied"
    )
    last_reminder_date = models.DateField(
        null=True, blank=True,
        editable=False,
        help_text="Date when the last reminder was sent"
    )
    payment_reminders_sent = models.PositiveIntegerField(
        default=0, 
        editable=False,
        help_text="Number of payment reminders sent"
    )
    minimum_payment_amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        default=Decimal('0.00'),
        help_text="Minimum payment amount if partial payments are allowed"
    )
    allow_partial_payments = models.BooleanField(
        default=False,
        editable=False,
        help_text="Whether partial payments are allowed"
    )

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
        """Calculate the amount paid toward this invoice so far.
        
        Note: This only includes COMPLETED payments, not PENDING ones.
        For pending payments, use the pending_payments property instead.
        """
        # Use prefetched payments if available
        if hasattr(self, '_prefetched_objects_cache') and 'payments' in self._prefetched_objects_cache:
            # Filter the prefetched payments to include only COMPLETED ones
            return sum(payment.amount for payment in self._prefetched_objects_cache['payments'] 
                      if payment.status == 'COMPLETED')
        
        # Otherwise query the database directly for COMPLETED payments
        return self.payments.filter(status='COMPLETED').aggregate(
            total=Sum('amount', default=0)
        )['total']
    
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
    
    
    
    def update_status_based_on_payments(self):
        """
        Update the invoice status based on payment status and due date.
        Called automatically when payments are created, updated, or deleted.
        """
        logger = logging.getLogger(__name__)
        
        # Don't change status for DRAFT or CANCELLED invoices
        if self.status in ['DRAFT', 'CANCELLED']:
            logger.debug(f"Not updating status for invoice {self.invoice_number} because it's {self.status}")
            return
            
        # Calculate totals using direct database queries to avoid caching issues
        total_amount = self.total_amount
        
        # Fetch the payments directly from the database to ensure fresh data
        completed_payments = self.payments.filter(status='COMPLETED').aggregate(
            total=Sum('amount', default=0)
        )['total']
        
        # Log the values being used for the calculation
        logger.info(f"Invoice {self.invoice_number} status update: " +
                   f"total_amount={total_amount}, " +
                   f"completed_payments={completed_payments}")
        
        old_status = self.status
        
        if completed_payments >= total_amount:
            self.status = 'PAID'
        elif completed_payments > 0:
            self.status = 'PARTIALLY_PAID'
        elif self.due_date < timezone.now().date():
            self.status = 'OVERDUE'
            
            # Check if we should apply late fee when status changes to OVERDUE
            if old_status != 'OVERDUE' and not self.late_fee_applied and self.late_fee_percentage > 0:
                self.apply_late_fee()
        else:
            self.status = 'PENDING'
            
        # Only save if status actually changed
        if old_status != self.status:
            logger.info(f"Changing invoice {self.invoice_number} status from {old_status} to {self.status}")
            self.save(update_fields=['status'])
    
    def clean(self):
        """Validate model fields."""
        super().clean()
        
        # If allow_partial_payments is True, minimum_payment_amount must be set
        if self.allow_partial_payments and self.minimum_payment_amount <= 0:
            raise ValidationError({
                'minimum_payment_amount': 'Minimum payment amount must be greater than 0 when partial payments are allowed.'
            })
            
        # If minimum_payment_amount is set but allow_partial_payments is False, warn about inconsistency
        if not self.allow_partial_payments and self.minimum_payment_amount > 0:
            raise ValidationError({
                'minimum_payment_amount': 'Minimum payment amount should be 0 when partial payments are not allowed.'
            })
            
        # Ensure due date is after issue date
        if self.due_date and self.issue_date and self.due_date < self.issue_date:
            raise ValidationError({
                'due_date': 'Due date cannot be before the issue date.'
            })
    
    def save(self, *args, **kwargs):
        """Override save to ensure validations are run."""
        self.clean()
        super().save(*args, **kwargs)
    
    @property
    def late_fee_amount(self):
        """Calculate the late fee for this invoice if it's overdue."""
        if self.status != 'OVERDUE' or self.late_fee_percentage <= 0:
            return Decimal('0.00')
        return (self.due_balance * self.late_fee_percentage / 100).quantize(Decimal('0.01'))
    
    @property
    def total_with_late_fees(self):
        """Calculate the total amount including any late fees."""
        return self.total_amount + self.late_fee_amount
    
    @property
    def payment_progress_percentage(self):
        """Calculate the payment progress as a percentage."""
        if self.total_amount <= 0:
            return 100
        return min(100, int((self.paid_amount / self.total_amount) * 100))
    
    def apply_late_fee(self):
        """Apply late fee to the invoice if it's overdue and fee hasn't been applied yet."""
        if self.status == 'OVERDUE' and not self.late_fee_applied and self.late_fee_percentage > 0:
            late_fee = self.late_fee_amount
            if late_fee > 0:
                InvoiceItem.objects.create(
                    invoice=self,
                    product="Late Payment Fee",
                    description=f"Late payment fee ({self.late_fee_percentage}%) applied on {timezone.now().date()}",
                    quantity=Decimal('1.00'),
                    unit_price=late_fee
                )
                
                self.late_fee_applied = True
                self.save(update_fields=['late_fee_applied'])
                return True
        return False

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
        ('PAYPAL', 'PayPal'),
        ('MON_CASH', 'Mon Cash'),
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
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='payments')
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
    
    def clean(self):
        """Validate payment data."""
        super().clean()
        
        # Check for zero amount
        if self.amount <= 0:
            raise ValidationError({
                'amount': 'Payment amount must be greater than zero.'
            })
        
        # Check if invoice is already paid
        if self.invoice_id and not self.pk:  # Only check on new payments
            invoice = Invoice.objects.get(pk=self.invoice_id)
            if invoice.status == 'PAID':
                raise ValidationError({
                    'invoice': 'Cannot add payment to an invoice that is already paid.'
                })
    
    def save(self, *args, **kwargs):
        """Override save to trigger invoice status update."""
        logger = logging.getLogger(__name__)
        
        # Run validations
        self.clean()
        
        is_new = not self.pk
        is_status_update = False
        
        # Check if this is a status update on an existing payment
        if not is_new:
            try:
                old_payment = Payment.objects.get(pk=self.pk)
                if old_payment.status != self.status:
                    is_status_update = True
                    logger.info(f"Payment {self.pk} status changing from {old_payment.status} to {self.status}")
            except Payment.DoesNotExist:
                pass
        
        # Auto-complete non-credit card payments on creation
        if is_new and self.payment_method in ['CASH', 'BANK_TRANSFER', 'OTHER'] and self.status == 'PENDING':
            self.status = 'COMPLETED'
            logger.info(f"Auto-completing {self.payment_method} payment")
        
        super().save(*args, **kwargs)
        
        # After saving, update the invoice status
        if is_status_update or is_new:
            logger.info(f"Updating invoice {self.invoice.invoice_number} status due to payment change")
        
        # Force a fresh calculation by using a database query instead of cached properties
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
