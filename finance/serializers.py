from rest_framework import serializers
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from .models import Client, Invoice, InvoiceItem, Payment
import uuid
from decimal import DecimalException


class ClientSerializer(serializers.ModelSerializer):
    total_paid = serializers.SerializerMethodField()
    total_outstanding = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    
    class Meta:
        model = Client
        fields = [
            'id', 'name', 'email', 'phone', 'company_name', 
            'tax_number', 'is_active', 'total_paid', 
            'total_outstanding', 'address', 'created_at',
        ]
        read_only_fields = ['created_at']
    
    def get_total_paid(self, obj):
        return obj.total_paid
    
    def get_total_outstanding(self, obj):
        return obj.total_outstanding
    
    def get_address(self, obj):
        if obj.address:
            return f"{obj.address.street}, {obj.address.city}, {obj.address.state} {obj.address.zip_code}, {obj.address.country}"
        return None


# ================================ Client Serializers ================================
class CreateClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['name', 'email', 'phone', 'company_name', 'tax_number', 'is_active']
        
    def validate_phone(self, value):
        # Basic phone number validation
        if not value.replace('+', '').replace('-', '').replace(' ', '').isdigit():
            raise serializers.ValidationError("Phone number must contain only digits, spaces, hyphens, or plus sign")
        return value
    
    def validate_email(self, value):
        if value and Client.objects.filter(email=value).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError("This email is already in use")
        return value
    
    def create(self, validated_data):
        organization_id = self.context['organization_id']
        validated_data['organization_id'] = organization_id
        return super().create(validated_data)
    
    
    def update(self, instance, validated_data):
        instance.name = validated_data.get('name', instance.name)
        instance.email = validated_data.get('email', instance.email)
        instance.phone = validated_data.get('phone', instance.phone)
        instance.company_name = validated_data.get('company_name', instance.company_name)
        instance.tax_number = validated_data.get('tax_number', instance.tax_number)
        instance.is_active = validated_data.get('is_active', instance.is_active)
        instance.save()
        return instance
    



# ================================ Invoice Item Serializers ================================
class InvoiceItemSerializer(serializers.ModelSerializer):
    total_amount = serializers.SerializerMethodField()
    
    class Meta:
        model = InvoiceItem
        fields = ['id', 'invoice', 'product', 'description', 'quantity', 'unit_price', 'total_amount']
        read_only_fields = ['total_amount']
    
    def get_total_amount(self, obj):
        return obj.total_amount
    
    def validate_quantity(self, value):
        if value <= Decimal('0'):
            raise serializers.ValidationError("Quantity must be greater than 0")
        return value
    
    def validate_unit_price(self, value):
        if value < Decimal('0'):
            raise serializers.ValidationError("Unit price cannot be negative")
        return value

# ================================ Invoice Item Serializers ================================
class SimpleInvoiceItemSerializer(serializers.ModelSerializer):
    total_amount = serializers.SerializerMethodField()
    
    class Meta:
        model = InvoiceItem
        fields = ['id', 'product', 'unit_price', 'quantity', 'total_amount']
        read_only_fields = ['total_amount']
    
    def get_total_amount(self, obj):
        return obj.total_amount


# ================================ Payment Serializers ================================
class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            'id', 'client', 'invoice', 'amount', 'payment_date',
            'payment_method', 'status', 'transaction_id', 'notes',
            'created_at'
        ]
        read_only_fields = ['created_at', 'status']
    
    def validate_amount(self, value):
        if value <= Decimal('0'):
            raise serializers.ValidationError("Payment amount must be greater than 0")
        return value
    
    def validate_payment_date(self, value):
        if value > timezone.now().date():
            raise serializers.ValidationError("Payment date cannot be in the future")
        return value
    
    def validate(self, data):
        invoice = data.get('invoice')
        if not invoice:
            raise serializers.ValidationError({
                "invoice": "Invoice is required"
            })
        
        # Check if invoice is in a valid state for payment
        valid_states = ['PENDING', 'OVERDUE', 'PARTIALLY_PAID']
        if invoice.status not in valid_states:
            raise serializers.ValidationError({
                "invoice": f"Cannot add payment to invoice in {invoice.status} status. Invoice must be in one of these states: {', '.join(valid_states)}"
            })
        
        # Validate payment amount doesn't exceed remaining balance
        remaining_balance = invoice.balance_due
        if data.get('amount') > remaining_balance:
            raise serializers.ValidationError({
                "amount": f"Payment amount ({data.get('amount')}) cannot exceed remaining balance ({remaining_balance})"
            })
        
        return data
    
    @transaction.atomic
    def create(self, validated_data):
        # Set initial payment status
        validated_data['status'] = 'PENDING'
        payment = super().create(validated_data)
        
        # Update invoice status based on payment
        self._update_invoice_status(payment)
        
        return payment
    
    def _update_invoice_status(self, payment):
        invoice = payment.invoice
        
        # Calculate total payments including the new one
        total_payments = sum(
            payment.amount for payment in Payment.objects.filter(
                invoice=invoice,
                status='COMPLETED'
            )
        ) + payment.amount
        
        # Update invoice status based on payment amount
        if total_payments >= invoice.total_amount:
            invoice.status = 'PAID'
        elif total_payments > 0:
            invoice.status = 'PARTIALLY_PAID'  # Changed from PENDING to PARTIALLY_PAID
        
        invoice.save()


# ================================ Invoice Serializers ================================
class InvoiceSerializer(serializers.ModelSerializer):
    items = SimpleInvoiceItemSerializer(many=True, read_only=True)
    subtotal_amount = serializers.SerializerMethodField()
    tax_amount = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    paid_amount = serializers.SerializerMethodField()
    balance_due = serializers.SerializerMethodField()
    is_fully_paid = serializers.SerializerMethodField()
    days_overdue = serializers.SerializerMethodField()
    client_name = serializers.SerializerMethodField()
    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'client_name', 'issue_date', 'due_date',
            'status', 'tax_rate', 'notes',
            'subtotal_amount', 'tax_amount', 'total_amount',
            'paid_amount', 'balance_due', 'is_fully_paid',
            'days_overdue', 'created_at', 'updated_at','items', 
        ]
        read_only_fields = [
            'invoice_number', 'created_at', 'updated_at',
            'subtotal_amount', 'tax_amount', 'total_amount',
            'paid_amount', 'balance_due', 'is_fully_paid'
        ]
        
    def get_client_name(self, obj):
        return obj.client.name
    
    def get_subtotal_amount(self, obj):
        return obj.subtotal_amount
    
    def get_tax_amount(self, obj):
        return obj.tax_amount
    
    def get_total_amount(self, obj):
        return obj.total_amount
    
    def get_paid_amount(self, obj):
        return obj.paid_amount
    
    def get_balance_due(self, obj):
        return obj.balance_due
    
    def get_is_fully_paid(self, obj):
        return obj.is_fully_paid
    
    def get_days_overdue(self, obj):
        if obj.status == 'OVERDUE':
            return (timezone.now().date() - obj.due_date).days
        return 0
    
    def validate_due_date(self, value):
        if value < self.initial_data.get('issue_date'):
            raise serializers.ValidationError("Due date cannot be before issue date")
        return value
    
    def validate_status(self, value):
        if self.instance and self.instance.status == 'PAID' and value != 'PAID':
            raise serializers.ValidationError("Cannot change status of a paid invoice")
        return value

# ================================ Invoice Item Serializers ================================
class CreateInvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ['product', 'description', 'quantity', 'unit_price']
        
    def validate_quantity(self, value):
        try:
            value = Decimal(str(value))
            if value <= Decimal('0'):
                raise serializers.ValidationError("Quantity must be greater than 0")
            return value
        except (TypeError, ValueError, DecimalException):
            raise serializers.ValidationError("Invalid decimal value")
    
    def validate_unit_price(self, value):
        try:
            value = Decimal(str(value))
            if value < Decimal('0'):
                raise serializers.ValidationError("Unit price cannot be negative")
            return value
        except (TypeError, ValueError, DecimalException):
            raise serializers.ValidationError("Invalid decimal value")

# ================================ Invoice Serializers ================================
class CreateInvoiceSerializer(serializers.ModelSerializer):
    items = CreateInvoiceItemSerializer(many=True)
    client_id = serializers.IntegerField()
    
    class Meta:
        model = Invoice
        fields = [
            'client_id', 'issue_date', 'due_date', 'tax_rate',
            'notes', 'items'
        ]
    
    def validate_client(self, value):
        try:
            organization_id = self.context.get('organization_id')
            client = Client.objects.filter(
                id=value,
                organization_id=organization_id,
                is_active=True
            ).first()
            
            if not client:
                raise serializers.ValidationError("Invalid or inactive client ID")
                
            return value
        except (TypeError, ValueError):
            raise serializers.ValidationError("Client ID must be a valid integer")
    
    def validate_tax_rate(self, value):
        try:
            value = Decimal(str(value))
            if value < Decimal('0') or value > Decimal('100'):
                raise serializers.ValidationError("Tax rate must be between 0 and 100")
            return value
        except (TypeError, ValueError, DecimalException):
            raise serializers.ValidationError("Invalid decimal value")
    
    def validate(self, data):
        # Check if issue date is not in the future
        if data.get('issue_date') and data['issue_date'] > timezone.now().date():
            raise serializers.ValidationError({
                "issue_date": "Issue date cannot be in the future"
            })
        
        # Check if due date is not before issue date
        if data.get('issue_date') and data.get('due_date') and data['due_date'] < data['issue_date']:
            raise serializers.ValidationError({
                "due_date": "Due date cannot be before issue date"
            })
        
        # Ensure there's at least one item
        if not data.get('items'):
            raise serializers.ValidationError({
                "items": "Invoice must have at least one item"
            })
        
        # Check for overdue invoices
        client_id = data.get('client')
        if client_id:
            overdue_invoices = Invoice.objects.filter(
                client_id=client_id,
                status='OVERDUE',
                due_date__lt=timezone.now().date()
            )
            if overdue_invoices.exists():
                raise serializers.ValidationError({
                    "client": "Client has overdue invoices that need to be settled first"
                })
        
        return data
    
    def generate_invoice_number(self):
        # Generate a unique invoice number (you can customize this format)
        prefix = timezone.now().strftime('%Y%m')
        random_suffix = str(uuid.uuid4().hex)[:6].upper()
        invoice_number = f"INV-{prefix}-{random_suffix}"
        
        # Ensure uniqueness
        while Invoice.objects.filter(invoice_number=invoice_number).exists():
            random_suffix = str(uuid.uuid4().hex)[:6].upper()
            invoice_number = f"INV-{prefix}-{random_suffix}"
        
        return invoice_number
    
    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        organization_id = self.context['organization_id']
        
        # Generate unique invoice number
        invoice_number = self.generate_invoice_number()
        
        # Create invoice with generated number and organization
        invoice = Invoice.objects.create(
            invoice_number=invoice_number,
            organization_id=organization_id,
            status='DRAFT',  # Always start as DRAFT
            **validated_data
        )
        
        # Create all items
        for item_data in items_data:
            InvoiceItem.objects.create(invoice=invoice, **item_data)
        
        return invoice
    
    @transaction.atomic
    def create_bulk(self, validated_data_list):
        """
        Create multiple invoices in a single transaction
        """
        invoices = []
        organization_id = self.context['organization_id']
        
        for validated_data in validated_data_list:
            items_data = validated_data.pop('items')
            invoice_number = self.generate_invoice_number()
            
            # Create invoice
            invoice = Invoice.objects.create(
                invoice_number=invoice_number,
                organization_id=organization_id,
                status='DRAFT',
                **validated_data
            )
            
            # Create items for this invoice
            for item_data in items_data:
                InvoiceItem.objects.create(invoice=invoice, **item_data)
            
            invoices.append(invoice)
        
        return invoices


# ================================ Invoice Serializers ================================     
class UpdateInvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, required=False)
    
    class Meta:
        model = Invoice
        fields = [
            'tax_rate', 'notes', 'items'  # Removed status from editable fields
        ]
    
    def validate(self, data):
        # Check if invoice is in an editable state
        editable_states = ['DRAFT', 'PENDING']
        if self.instance.status not in editable_states:
            raise serializers.ValidationError({
                "non_field_errors": f"Cannot modify invoice in {self.instance.status} status. Only invoices in these states can be modified: {', '.join(editable_states)}"
            })
        
        # Validate tax rate changes
        if 'tax_rate' in data:
            try:
                tax_rate = Decimal(str(data['tax_rate']))
                if tax_rate < Decimal('0') or tax_rate > Decimal('100'):
                    raise serializers.ValidationError({
                        "tax_rate": "Tax rate must be between 0 and 100"
                    })
            except (TypeError, ValueError, DecimalException):
                raise serializers.ValidationError({
                    "tax_rate": "Invalid decimal value for tax rate"
                })
        
        # Validate items if provided
        if 'items' in data:
            if not data['items']:
                raise serializers.ValidationError({
                    "items": "Invoice must have at least one item"
                })
            
            # Validate each item's quantity and unit price
            for item in data['items']:
                if 'quantity' in item and item['quantity'] <= 0:
                    raise serializers.ValidationError({
                        "items": "Item quantity must be greater than 0"
                    })
                if 'unit_price' in item and item['unit_price'] < 0:
                    raise serializers.ValidationError({
                        "items": "Item unit price cannot be negative"
                    })
        
        return data
    
    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        
        if items_data is not None:
            # Delete existing items only if invoice is in DRAFT or PENDING status
            if instance.status in ['DRAFT', 'PENDING']:
                instance.items.all().delete()
                # Create new items
                for item_data in items_data:
                    InvoiceItem.objects.create(invoice=instance, **item_data)
            else:
                raise serializers.ValidationError({
                    "items": "Cannot modify items for invoices not in DRAFT or PENDING status"
                })
        
        # Update invoice fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        return instance
        
        