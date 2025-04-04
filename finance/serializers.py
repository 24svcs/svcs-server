from rest_framework import serializers
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from .models import Client, Invoice, InvoiceItem, Payment
import uuid


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


class SimpleInvoiceItemSerializer(serializers.ModelSerializer):
    total_amount = serializers.SerializerMethodField()
    
    class Meta:
        model = InvoiceItem
        fields = ['id', 'product', 'unit_price', 'quantity', 'total_amount']
        read_only_fields = ['total_amount']
    
    def get_total_amount(self, obj):
        return obj.total_amount


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            'id', 'client', 'invoice', 'amount', 'payment_date',
            'payment_method', 'status', 'transaction_id', 'notes',
            'created_at'
        ]
        read_only_fields = ['created_at']
    
    def validate_amount(self, value):
        if value <= Decimal('0'):
            raise serializers.ValidationError("Payment amount must be greater than 0")
        return value
    
    def validate_payment_date(self, value):
        if value > timezone.now().date():
            raise serializers.ValidationError("Payment date cannot be in the future")
        return value


class InvoiceSerializer(serializers.ModelSerializer):
    items = SimpleInvoiceItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    subtotal_amount = serializers.SerializerMethodField()
    tax_amount = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    paid_amount = serializers.SerializerMethodField()
    balance_due = serializers.SerializerMethodField()
    is_fully_paid = serializers.SerializerMethodField()
    days_overdue = serializers.SerializerMethodField()
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'client', 'issue_date', 'due_date',
            'status', 'tax_rate', 'notes', 'items', 'payments',
            'subtotal_amount', 'tax_amount', 'total_amount',
            'paid_amount', 'balance_due', 'is_fully_paid',
            'days_overdue', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'invoice_number', 'created_at', 'updated_at',
            'subtotal_amount', 'tax_amount', 'total_amount',
            'paid_amount', 'balance_due', 'is_fully_paid'
        ]
    
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


class CreateInvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True)
    
    class Meta:
        model = Invoice
        fields = [
            'client', 'issue_date', 'due_date', 'tax_rate',
            'notes', 'items'
        ]
    
    def validate(self, data):
        # Check if issue date is not in the future
        if data['issue_date'] > timezone.now().date():
            raise serializers.ValidationError({
                "issue_date": "Issue date cannot be in the future"
            })
        
        # Check if due date is not before issue date
        if data['due_date'] < data['issue_date']:
            raise serializers.ValidationError({
                "due_date": "Due date cannot be before issue date"
            })
        
        # Validate tax rate is within reasonable bounds
        if data['tax_rate'] < 0 or data['tax_rate'] > 100:
            raise serializers.ValidationError({
                "tax_rate": "Tax rate must be between 0 and 100"
            })
        
        # Ensure there's at least one item
        if not data.get('items'):
            raise serializers.ValidationError({
                "items": "Invoice must have at least one item"
            })
            
        # Validate client exists and is active
        client = Client.objects.filter(id=data['client'], is_active=True).first()
        if not client:
            raise serializers.ValidationError({
                "client": "Invalid or inactive client"
            })
        
        # Optional: Check if client has any overdue invoices
        overdue_invoices = Invoice.objects.filter(
            client=client,
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
        
        # Generate unique invoice number
        invoice_number = self.generate_invoice_number()
        
        # Create invoice with generated number
        invoice = Invoice.objects.create(
            invoice_number=invoice_number,
            **validated_data
        )
        
        # Create all items
        for item_data in items_data:
            InvoiceItem.objects.create(invoice=invoice, **item_data)
        
        # Optional: Send notification to client
        self.send_invoice_notification(invoice)
        
        return invoice
    
    def send_invoice_notification(self, invoice):
        # This is a placeholder for sending notifications
        # You would implement this based on your notification system
        pass


class UpdateInvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, required=False)
    
    class Meta:
        model = Invoice
        fields = [
            'status', 'tax_rate', 'notes', 'items'
        ]
    
    def validate(self, data):
        if self.instance.status == 'PAID':
            raise serializers.ValidationError("Cannot modify a paid invoice")
        return data
    
    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        
        if items_data is not None:
            # Delete existing items
            instance.items.all().delete()
            # Create new items
            for item_data in items_data:
                InvoiceItem.objects.create(invoice=instance, **item_data)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        return instance
        
        