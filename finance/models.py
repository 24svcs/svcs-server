from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from organization.models import Organization
from django.utils import timezone


class Address(models.Model):
    street = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=50)
    zip_code = models.CharField(max_length=10)
    country = models.CharField(max_length=100, default='United States')
    
    def __str__(self):
        return f"{self.street}, {self.city}, {self.state} {self.zip_code}"

class Client(models.Model):
    organization = models.ForeignKey(Organization, models.CASCADE, related_name='clients_c')
    name = models.CharField(max_length=200)
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(unique=True)
    address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name='address', null=True)
    company_name = models.CharField(max_length=200, blank=True)
    tax_number = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
    
    @property
    def total_paid(self):
        return sum(payment.amount for payment in self.payments.all())
    
    @property
    def total_outstanding(self):
        return sum(invoice.total_amount for invoice in self.invoices.all()) - self.total_paid
    
    class Meta:
        ordering = ['name', 'company_name']



#TODO make the id a uuid field
class Invoice(models.Model):
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PENDING', 'Pending'),
        ('PAID', 'Paid'),
        ('OVERDUE', 'Overdue'),
        ('CANCELLED', 'Cancelled'),
        ('PARTIALLY_PAID', 'Partially Paid'),
    ]
    organization = models.ForeignKey(Organization, models.CASCADE, related_name='clients')
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
    def subtotal_amount(self):
        return sum(item.total_amount for item in self.items.all())

    @property
    def tax_amount(self):
        return self.subtotal_amount * (self.tax_rate / Decimal('100'))

    @property
    def total_amount(self):
        return self.subtotal_amount + self.tax_amount
    
    @property
    def paid_amount(self):
        return sum(
            payment.amount 
            for payment in self.payments.filter(status='COMPLETED')
        )
    
    @property
    def pending_amount(self):
        return sum(
            payment.amount 
            for payment in self.payments.filter(status='PENDING')
        )
    
    @property
    def balance_due(self):
        return self.total_amount - self.paid_amount
    
    @property
    def is_fully_paid(self):
        return self.balance_due <= Decimal('0.00')
    

    def update_status_based_on_payments(self):
        """
        Update invoice status based on payments
        """
        if self.status in ['DRAFT', 'CANCELLED']:
            return
        
        total_paid = self.paid_amount
        total_pending = self.pending_amount
        
        if total_paid >= self.total_amount:
            self.status = 'PAID'
        elif total_paid > 0 or total_pending > 0:
            self.status = 'PARTIALLY_PAID'
        elif self.due_date < timezone.now().date():
            self.status = 'OVERDUE'
        else:
            self.status = 'PENDING'
        
        self.save()

class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    product = models.CharField(max_length=255)
    description = models.CharField(max_length=255)
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
    def total_amount(self):
        return self.quantity * self.unit_price

class Payment(models.Model):
    organization = models.ForeignKey(Organization, models.CASCADE, related_name='clients_p')
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
    
    @property
    def pending_amount(self):
        """
        Returns the pending amount based on payment status.
        If status is PENDING, returns the payment amount, otherwise returns 0.
        """
        return self.amount if self.status == 'PENDING' else Decimal('0.00')
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update invoice status after payment status changes
        self.invoice.update_status_based_on_payments()
