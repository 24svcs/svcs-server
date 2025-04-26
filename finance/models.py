from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from organization.models import Organization
from django.utils import timezone
import uuid
from phonenumber_field.modelfields import PhoneNumberField
from django_countries.fields import CountryField
import logging
from django.db.models import Sum, F
from django.core.exceptions import ValidationError
import calendar
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta


# <==============================>  Address Model <==========================================>
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
    client = models.OneToOneField('Client', on_delete=models.CASCADE, related_name='address')
    
    def __str__(self):
        return f"{self.street}, {self.city}, {self.state} {self.zip_code}"
    

# <==============================>  Client Model <==========================================>

class Client(models.Model):
    """
    Client model representing customers in the system.
    Contains basic information and relationships to invoices and payments.
    """
    
    ACTIVE = 'ACTIVE'
    INACTIVE = 'INACTIVE'
    BANNED = 'BANNED'
    
    MEMBER_STATUS_CHOICES = [
        (ACTIVE, 'Active'),
        (INACTIVE, 'Inactive'),
        (BANNED, 'Banned'),

    ]
    organization = models.ForeignKey(Organization, models.CASCADE, related_name='clients')
    name = models.CharField(max_length=200)
    email = models.EmailField(null=True, blank=True)
    phone = PhoneNumberField()
    tax_number = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=20, choices=MEMBER_STATUS_CHOICES, default=ACTIVE)
    stripe_customer_id = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name
    
    @property
    def total_paid(self):
        """
        Calculate the total amount paid by this client across all invoices.
        Optimized to use prefetched payments if available.
        """
        if hasattr(self, '_prefetched_objects_cache') and 'payments' in self._prefetched_objects_cache:
            return sum(payment.amount for payment in self._prefetched_objects_cache['payments'] 
                      if payment.status == 'COMPLETED')
        return sum(payment.amount for payment in self.payments.filter(status='COMPLETED'))
    
    @property
    def total_outstanding(self):
        """
        Calculate the total outstanding balance for this client across all invoices.
        Optimized to use prefetched invoices with annotated totals.
        """
        if hasattr(self, '_prefetched_objects_cache') and 'invoices' in self._prefetched_objects_cache:
            total_invoice_amount = sum(invoice.invoice_total for invoice in self._prefetched_objects_cache['invoices'])
            return total_invoice_amount - self.total_paid
        
        # Fallback if prefetched data is not available
        total_invoice_amount = self.invoices.aggregate(
            total=Sum(F('items__quantity') * F('items__unit_price') * (1 + F('tax_rate') / 100))
        )['total'] or 0
        return total_invoice_amount - self.total_paid
    
    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['email']),
            models.Index(fields=['phone']),
            models.Index(fields=['status']),
        ]
        
   
    

# <==============================>  Invoice Model <==========================================>

class Invoice(models.Model):
    """
    Invoice model representing financial documents issued to clients.
    Includes status tracking, payment linkage, and calculation properties.
    """
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ISSUED', 'Issued'),
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
    late_fee_amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        default=Decimal('0.00'),
        editable=False,
        help_text="Late fee amount"
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
        return (items_total * self.tax_rate / 100).quantize(Decimal('0.01'))
    
    
    
    @property
    def total_amount(self):
        """Calculate the total invoice amount including tax and late fees."""
        # Using prefetched items if available
        if hasattr(self, '_prefetched_objects_cache') and 'items' in self._prefetched_objects_cache:
            items_total = sum(item.amount for item in self._prefetched_objects_cache['items'])
        else:
            items_total = sum(item.amount for item in self.items.all())
        
        # Calculate base total with tax
        base_total = (items_total + (items_total * self.tax_rate / 100)).quantize(Decimal('0.01'))
        
        # Add late fee if it has been applied
        if self.late_fee_applied and self.late_fee_amount > 0:
            return base_total + self.late_fee_amount
        
        return base_total
    
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
        elif completed_payments > 0 and self.due_date > timezone.now().date():
            self.status = 'PARTIALLY_PAID'
        elif self.due_date < timezone.now().date():
            self.status = 'OVERDUE'
            
            # Check if we should apply late fee when status changes to OVERDUE
            if old_status != 'OVERDUE' and not self.late_fee_applied and self.late_fee_percentage > 0:
                # Calculate base total without late fees
                if hasattr(self, '_prefetched_objects_cache') and 'items' in self._prefetched_objects_cache:
                    items_total = sum(item.amount for item in self._prefetched_objects_cache['items'])
                else:
                    items_total = sum(item.amount for item in self.items.all())
                
                base_total = (items_total + (items_total * self.tax_rate / 100)).quantize(Decimal('0.01'))
                unpaid_base = base_total - completed_payments
                
                # Calculate and set late fee amount
                self.late_fee_amount = (unpaid_base * self.late_fee_percentage / 100).quantize(Decimal('0.01'))
                self.late_fee_applied = True
                
                # Save both fields in a single update
                self.save(update_fields=['status', 'late_fee_amount', 'late_fee_applied'])
                return
        else:
            self.status = 'ISSUED'
            
        # Only save if status actually changed
        if old_status != self.status:
            logger.info(f"Changing invoice {self.invoice_number} status from {old_status} to {self.status}")
            self.save(update_fields=['status'])
    
    def clean(self):
        """Validate invoice data."""
        super().clean()
        
        # Validate dates
        if self.due_date and self.issue_date and self.due_date < self.issue_date:
            raise ValidationError({
                'due_date': 'Due date cannot be before issue date.'
            })
            
        # Validate minimum payment amount
        if self.allow_partial_payments and self.minimum_payment_amount:
            # Only validate if we have a minimum payment amount
            if self.minimum_payment_amount < Decimal('0.50'):
                raise ValidationError({
                    'minimum_payment_amount': 'Minimum payment amount must be at least $0.50.'
                })
                
        # Validate late fee percentage
        if self.late_fee_percentage < Decimal('0') or self.late_fee_percentage > Decimal('100'):
            raise ValidationError({
                'late_fee_percentage': 'Late fee percentage must be between 0 and 100.'
            })

    def save(self, *args, **kwargs):
        """Override save to ensure validations are run and handle invoice number generation."""
        if not self.invoice_number:
            # Generate invoice number if not set
            prefix = self.organization.invoice_number_prefix if hasattr(self.organization, 'invoice_number_prefix') else 'INV'
            last_invoice = Invoice.objects.filter(organization=self.organization).order_by('-invoice_number').first()
            if last_invoice and last_invoice.invoice_number:
                try:
                    last_number = int(last_invoice.invoice_number.split('-')[-1])
                    self.invoice_number = f"{prefix}-{str(last_number + 1).zfill(6)}"
                except (ValueError, IndexError):
                    self.invoice_number = f"{prefix}-{str(uuid.uuid4().hex[:6]).upper()}"
            else:
                self.invoice_number = f"{prefix}-{100001}"
                
        self.clean()
        super().save(*args, **kwargs)

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
                self.late_fee_applied = True
                self.save(update_fields=['late_fee_applied'])
                return True
        return False
    
    class Meta:
        ordering = ['issue_date']
        indexes = [
            models.Index(fields=['issue_date']),
            models.Index(fields=['due_date']),
            models.Index(fields=['status'])
        ]
        
# <==============================>  Invoice Item Model <==========================================>
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
        return (self.quantity * self.unit_price).quantize(Decimal('0.01'))
    
    
#=========================================== PAYMENTS ===================================================

class Payment(models.Model):
    """
    Payment record associated with an invoice and client.
    Tracks payment status, method, and related transaction details.
    """
    PAYMENT_METHOD_CHOICES = [
        ('CASH', 'Cash'),
        ('BANK_TRANSFER', 'Bank Transfer'),
        ('CREDIT_CARD', 'Credit Card'),
        ('WIRE_TRANSFER', 'Wire Transfer'),
        ('CHECK', 'Check'),
        ('PAYPAL', 'PayPal'),
        ('MON_CASH', 'MonCash'),
        ('NAT_CASH', 'NatCash'),
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
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
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
        if is_new and self.payment_method in ['CASH', 'BANK_TRANSFER', 'WIRE_TRANSFER', 'CHECK'] and self.status == 'PENDING':
            self.status = 'COMPLETED'
            logger.info(f"Auto-completing {self.payment_method} payment")
        
        super().save(*args, **kwargs)
        
        # After saving, update the invoice status
        if is_status_update or is_new:
            logger.info(f"Updating invoice {self.invoice.invoice_number} status due to payment change")
        
        # Force a fresh calculation by using a database query instead of cached properties
        self.invoice.update_status_based_on_payments()
        
        
        
        
        

# <==============================>  Recurring Invoice Model <==========================================>

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
        
        

# <==============================>  Recurring Invoice Item Model <==========================================>
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
        return (self.quantity * self.unit_price).quantize(Decimal('0.01'))






# <==============================>  Expense Model <==========================================>

class Expense(models.Model):
    EXPENSE_CATEGORY_CHOICES  = [
        # Business/Company Expenses
        ('PAYROLL', 'Payroll & Benefits'),
        ('RENT', 'Rent & Utilities'),
        ('OFFICE_SUPPLIES', 'Office Supplies'),
        ('EQUIPMENT', 'Equipment & Machinery'),
        ('SOFTWARE', 'Software & Technology'),
        ('MARKETING', 'Marketing & Advertising'),
        ('TRAVEL', 'Travel & Entertainment'),
        ('PROFESSIONAL_SERVICES', 'Professional Services'),
        ('INSURANCE_BUSINESS', 'Business Insurance'),
        ('TAXES', 'Taxes & Licenses'),
        ('MAINTENANCE', 'Maintenance & Repairs'),
        ('TRAINING', 'Training & Development'),
        ('SUBSCRIPTIONS', 'Subscriptions & Memberships'),
        ('INVENTORY', 'Inventory & Supplies'),
        ('SHIPPING', 'Shipping & Logistics'),
        ('LEGAL', 'Legal & Professional Fees'),
        ('BANK_FEES', 'Bank & Financial Fees'),
        ('RESEARCH', 'Research & Development'),
        
        # Personal/Individual Expenses
        ('HOUSING', 'Housing & Rent'),
        ('TRANSPORTATION', 'Transportation'),
        ('FOOD', 'Food & Dining'),
        ('UTILITIES', 'Personal Utilities'),
        ('ENTERTAINMENT', 'Entertainment'),
        ('INSURANCE_PERSONAL', 'Personal Insurance'),
        ('HEALTHCARE', 'Healthcare & Medical'),
        ('EDUCATION', 'Education'),
        ('GIFTS', 'Gifts & Donations'),
        ('DEBT', 'Debt Payments'),
        ('PERSONAL', 'Personal Care'),
        ('INVESTMENTS', 'Investments'),
        ('CHILDCARE', 'Childcare'),
        ('PETS', 'Pet Expenses'),
        ('CLOTHING', 'Clothing'),
        ('OTHER', 'Other Expenses'),
    ]

    FREQUENCY_CHOICES = [
        ('DAILY', 'Daily'),
        ('WEEKLY', 'Weekly'),
        ('BIWEEKLY', 'Bi-Weekly'),
        ('MONTHLY', 'Monthly'),
        ('QUARTERLY', 'Quarterly'), 
        ('BIANNUAL', 'Bi-Annual'),
        ('YEARLY', 'Yearly'),
    ]

    EXPENSE_TYPE_CHOICES = [
        ('RECURRING', 'Recurring'),
        ('ONE_TIME', 'One Time'),
    ]

    RECURRING_STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('CANCELLED', 'Cancelled'),
        ('PAUSED', 'Paused'),
        ('ENDED', 'Ended'),  # For subscriptions with end date
    ]

    organization = models.ForeignKey(Organization, models.CASCADE, related_name='expenses')
    name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    category = models.CharField(max_length=30, choices=EXPENSE_CATEGORY_CHOICES)
    expense_type = models.CharField(max_length=20, choices=EXPENSE_TYPE_CHOICES, default='ONE_TIME')
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, null=True, blank=True)
    date = models.DateField(help_text="Start date for recurring expenses, or expense date for one-time expenses")
    billing_day = models.PositiveIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1)],
        help_text="Day of the period when billing occurs (e.g., day of month for monthly billing)"
    )
    recurring_status = models.CharField(
        max_length=20, 
        choices=RECURRING_STATUS_CHOICES,
        null=True, blank=True,
        help_text="Status of recurring expense subscription"
    )
    end_date = models.DateField(
        null=True, blank=True,
        help_text="Optional end date for recurring expenses"
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def clean(self):
        """Validate expense data."""
        super().clean()
        
        # Validate frequency for recurring expenses
        if self.expense_type == 'RECURRING':
            if not self.frequency:
                raise ValidationError({
                    'frequency': 'Frequency is required for recurring expenses.'
                })
            if not self.billing_day:
                raise ValidationError({
                    'billing_day': 'Billing day is required for recurring expenses.'
                })
            if not self.recurring_status:
                self.recurring_status = 'ACTIVE'  # Default to active for new recurring expenses
        else:
            # Clear recurring-specific fields for one-time expenses
            self.frequency = None
            self.billing_day = None
            self.recurring_status = None
            self.end_date = None

        # Validate billing day based on frequency
        if self.expense_type == 'RECURRING' and self.frequency and self.billing_day:
            if self.frequency == 'MONTHLY' and self.billing_day > 31:
                raise ValidationError({
                    'billing_day': 'Day of month cannot be greater than 31.'
                })
            elif self.frequency == 'WEEKLY' and self.billing_day > 7:
                raise ValidationError({
                    'billing_day': 'Day of week cannot be greater than 7.'
                })
            elif self.frequency == 'YEARLY' and self.billing_day > 366:
                raise ValidationError({
                    'billing_day': 'Day of year cannot be greater than 366.'
                })

        # Validate end_date if provided
        if self.end_date and self.date and self.end_date < self.date:
            raise ValidationError({
                'end_date': 'End date cannot be before start date.'
            })

        # Auto-update status if end_date is reached
        if self.end_date and self.end_date < timezone.now().date():
            self.recurring_status = 'ENDED'

    def get_next_billing_date(self):
        """
        Calculate the next billing date based on frequency and billing day.
        
        This method handles different frequencies in a realistic way:
        - Monthly: Bills on specific day of month (e.g., 15th of each month)
        - Weekly: Bills on specific day of week (1=Monday through 7=Sunday)
        - Yearly: Bills on specific day of year (1-366)
        - Quarterly: Bills on specific day within each quarter
        - Biannual: Bills on specific day within each 6-month period
        - Daily: Bills every day
        
        Returns:
            date: The next billing date or None if not applicable
        """
        if (not self.frequency or 
            not self.billing_day or 
            self.expense_type != 'RECURRING' or
            self.recurring_status != 'ACTIVE'):
            return None

        today = timezone.now().date()
        
        # If end_date is set and passed, no more billing
        if self.end_date and self.end_date < today:
            return None
        
        if self.frequency == 'MONTHLY':
            # Start with this month's billing day
            next_date = date(today.year, today.month, 
                           min(self.billing_day, calendar.monthrange(today.year, today.month)[1]))
            # If that's in the past or today, move to next month
            if next_date <= today:
                next_month = today + relativedelta(months=1)
                next_date = date(next_month.year, next_month.month, 
                               min(self.billing_day, calendar.monthrange(next_month.year, next_month.month)[1]))
        
        elif self.frequency == 'WEEKLY':
            # Get next occurrence of the day of week (1=Monday through 7=Sunday)
            current_day = today.isoweekday()
            days_ahead = self.billing_day - current_day
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7
            next_date = today + timedelta(days=days_ahead)
        
        elif self.frequency == 'YEARLY':
            # Get next occurrence of the day of year
            current_year = today.year
            try:
                next_date = date(current_year, 1, 1) + timedelta(days=self.billing_day - 1)
                if next_date <= today:
                    next_date = date(current_year + 1, 1, 1) + timedelta(days=self.billing_day - 1)
            except ValueError:  # Handle leap year
                next_date = date(current_year, 12, 31)
        
        elif self.frequency == 'QUARTERLY':
            # Get next quarter's billing day
            current_quarter = (today.month - 1) // 3
            quarter_start = date(today.year, current_quarter * 3 + 1, 1)
            next_date = quarter_start + timedelta(days=self.billing_day - 1)
            if next_date <= today:
                next_quarter = quarter_start + relativedelta(months=3)
                next_date = next_quarter + timedelta(days=self.billing_day - 1)
        
        elif self.frequency == 'BIANNUAL':
            # Get next semi-annual billing day
            current_half = (today.month - 1) // 6
            half_start = date(today.year, current_half * 6 + 1, 1)
            next_date = half_start + timedelta(days=self.billing_day - 1)
            if next_date <= today:
                next_half = half_start + relativedelta(months=6)
                next_date = next_half + timedelta(days=self.billing_day - 1)
        
        elif self.frequency == 'BIWEEKLY':
            # Similar to weekly but with 2-week intervals
            current_day = today.isoweekday()
            days_ahead = self.billing_day - current_day
            if days_ahead <= 0:
                days_ahead += 14
            next_date = today + timedelta(days=days_ahead)
        
        elif self.frequency == 'DAILY':
            next_date = today + timedelta(days=1)
            
        # If end_date is set, don't return dates beyond it
        if self.end_date and next_date > self.end_date:
            return None
            
        return next_date

    def should_generate_expense(self):
        """
        Check if a new expense instance should be generated based on:
        - Expense must be recurring and active
        - Next billing date should be today or in the past
        - End date (if set) should not be passed
        """
        if (self.expense_type != 'RECURRING' or 
            self.recurring_status != 'ACTIVE'):
            return False
            
        next_billing = self.get_next_billing_date()
        if not next_billing:
            return False
            
        return next_billing <= timezone.now().date()

    def generate_next_expense(self):
        """
        Generate a new one-time expense instance based on this recurring expense.
        Returns the new expense instance (unsaved) or None if not applicable.
        """
        if not self.should_generate_expense():
            return None
            
        next_billing = self.get_next_billing_date()
        
        return Expense(
            organization=self.organization,
            name=self.name,
            amount=self.amount,
            category=self.category,
            expense_type='ONE_TIME',
            date=next_billing,
            notes=f"Auto-generated from recurring expense: {self.name}"
        )

    def __str__(self):
        base_str = f"{self.name} - {self.amount} - {self.category}"
        if self.expense_type == 'RECURRING':
            status_str = f" [{self.recurring_status}]" if self.recurring_status else ""
            next_date = self.get_next_billing_date()
            billing_info = f" (Recurring: {self.frequency}, Next billing: {next_date})" if next_date else f" (Recurring: {self.frequency})"
            return f"{base_str}{billing_info}{status_str} - {self.date}"
        return f"{base_str} - {self.date}"

    @property
    def is_due_soon(self):
        """Check if the expense is due within the next 7 days."""
        next_date = self.get_next_billing_date()
        if not next_date:
            return False
        return 0 <= (next_date - timezone.now().date()).days <= 7

    def reactivate_subscription(self):
        """
        Safely reactivate a cancelled recurring subscription.
        Returns True if reactivation was successful, False otherwise.
        """
        if self.expense_type != 'RECURRING':
            raise ValidationError('Can only reactivate recurring expenses.')
            
        if self.recurring_status not in ['CANCELLED', 'PAUSED']:
            raise ValidationError('Can only reactivate cancelled or paused expenses.')
            
        # Check if this is the most recent version of this subscription
        latest_expense = Expense.objects.filter(
            organization=self.organization,
            name=self.name,
            expense_type='RECURRING'
        ).order_by('-date').first()
        
        if latest_expense.id != self.id:
            raise ValidationError('Can only reactivate the most recent version of a subscription.')
            
        # If there's an end_date in the past, clear it since we're reactivating
        if self.end_date and self.end_date < timezone.now().date():
            self.end_date = None
            
        self.recurring_status = 'ACTIVE'
        self.save()
        
        return True

    class Meta:
        ordering = ['-date']
        indexes = [
            models.Index(fields=['category']),
            models.Index(fields=['date']),
            models.Index(fields=['expense_type']),
            models.Index(fields=['recurring_status']),
        ]
    
    
    