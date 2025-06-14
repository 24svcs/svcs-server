from rest_framework import serializers
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from .models import Client, Invoice, InvoiceItem, Payment, RecurringInvoice, RecurringInvoiceItem

from decimal import DecimalException
from .utils import annotate_invoice_calculations
from .serializers.client_serializers import SimpleClientSerializer


# ================================ Invoice Item Serializers ================================
class InvoiceItemSerializer(serializers.ModelSerializer):
    total_amount = serializers.SerializerMethodField()
    
    class Meta:
        model = InvoiceItem
        fields = ['id', 'invoice', 'product', 'description', 'quantity', 'unit_price', 'total_amount']
        read_only_fields = ['total_amount']
    
    def get_total_amount(self, obj):
        return obj.amount
    
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
    class Meta:
        model = InvoiceItem
        fields = ['id', 'product', 'unit_price', 'quantity']
    

# ================================ Payment Serializers ================================
class PaymentSerializer(serializers.ModelSerializer):
    invoice_id = serializers.IntegerField()
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)
    client_name = serializers.CharField(source='client.name', read_only=True)
    payment_date = serializers.DateField(required=False)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'invoice_number', 'client_name', 'amount', 'payment_date',
            'payment_method', 'status', 'transaction_id', 'notes', 'invoice_id', 
        ]
        read_only_fields = ['status']
    
    def validate_payment_method(self, value):
        allowed_methods = ['CASH', 'BANK_TRANSFER', 'WIRE_TRANSFER', 'CHECK', 'NAT_CASH']
        if value not in allowed_methods:
            raise serializers.ValidationError(
                f"Only manual payment methods ({', '.join(allowed_methods)}) are allowed. "
                "Other payment types must be processed through their respective payment gateways."
            )
        return value

class CreatePaymentSerializer(serializers.ModelSerializer):
    invoice_id = serializers.IntegerField()
    payment_date = serializers.DateField(required=False)
    
    class Meta:
        model = Payment
        fields = ['invoice_id', 'amount', 'payment_method', 'notes', 'payment_date']
    
    def validate_invoice_id(self, value):
        try:
            # Simply check if the invoice exists
            invoice = Invoice.objects.get(pk=value)
            return value
        except Invoice.DoesNotExist:
            raise serializers.ValidationError("Invalid invoice ID")
    
    def validate_amount(self, value):
        if value <= Decimal('0'):
            raise serializers.ValidationError("Payment amount must be greater than 0")
        return value
    
    def validate_payment_method(self, value):
        allowed_methods = ['CASH', 'BANK_TRANSFER', 'WIRE_TRANSFER', 'CHECK', 'NAT_CASH']
        if value not in allowed_methods:
            raise serializers.ValidationError(
                f"Only manual payment methods ({', '.join(allowed_methods)}) are allowed. "
                "Other payment types must be processed through their respective payment gateways."
            )
        return value
        
    def validate_payment_date(self, value):
        if value and value > timezone.now().date():
            raise serializers.ValidationError("Payment date cannot be in the future")
        return value
    
    def validate(self, data):
        # Get invoice with annotations for calculations
        invoice = annotate_invoice_calculations(
            Invoice.objects.filter(id=data['invoice_id'])
        ).get()
        
        # Check if invoice belongs to the same organization
        organization_id = self.context.get('organization_id')
        if not organization_id:
            raise serializers.ValidationError({
                "organization_id": "Organization ID is required in context"
            })
            
        if str(invoice.organization_id) != str(organization_id):
            raise serializers.ValidationError({
                "invoice_id": f"Invoice organization ID ({invoice.organization_id}) does not match request organization ID ({organization_id})"
            })
        
        # Check if invoice can accept payments
        if invoice.status not in ['ISSUED', 'OVERDUE', 'PARTIALLY_PAID']:
            raise serializers.ValidationError({
                "invoice_id": f"Cannot add payment to invoice in {invoice.status} status. "
                "Invoice must be ISSUED, OVERDUE, or PARTIALLY_PAID"
            })
            
        # Check if payment date is before invoice issue date
        payment_date = data.get('payment_date', timezone.now().date())
        if payment_date < invoice.issue_date:
            raise serializers.ValidationError({
                "payment_date": f"Payment date cannot be before invoice issue date ({invoice.issue_date})"
            })
            
        # Check if payment date is in the future
        if payment_date > timezone.now().date():
            raise serializers.ValidationError({
                "payment_date": "Payment date cannot be in the future"
            })
            
        # Check if payment amount is too small
        if data['amount'] < Decimal('0.01'):
            raise serializers.ValidationError({
                "amount": "Payment amount must be at least $0.01"
            })
            
        # Check if there are any pending payments for this invoice
        pending_payments_exist = invoice.payments.filter(status='PENDING').exists()
        if pending_payments_exist:
            raise serializers.ValidationError({
                "invoice_id": "This invoice already has a pending payment. Please wait for the pending payment to be processed before adding a new payment."
            })
        
        # Calculate the due balance amount to pay
        balance = invoice.due_balance
        
        # Check if payment amount exceeds remaining balance
        if data['amount'] > balance:
            raise serializers.ValidationError({
                "amount": f"Payment amount ({data['amount']}) cannot exceed due balance ({balance})."
            })
        
        # Check for partial payment restrictions
        if data['amount'] < balance:  # This is likely a partial payment
            if not invoice.allow_partial_payments:
                raise serializers.ValidationError({
                    "amount": f"This invoice does not allow partial payments. Payment amount must be {balance}."
                })
            
            # Check if payment meets minimum amount requirement
            # Allow payment if it equals the due balance, even if less than minimum
            if data['amount'] < invoice.minimum_payment_amount and data['amount'] != balance:
                raise serializers.ValidationError({
                    "amount": f"Payment amount must be at least {invoice.minimum_payment_amount} for partial payments or equal to the remaining balance ({balance})."
                })
        
        # Check if payment is too small to be practical (e.g., less than $0.50)
        # Skip this check for final payments that clear the balance
        if data['amount'] < Decimal('0.50') and data['amount'] != balance:
            raise serializers.ValidationError({
                "amount": "Payment amount is too small. Minimum payment amount should be at least $0.50 unless it's the final payment that clears the balance."
            })
        
        # Validate payment date isn't in the future if provided
        if 'payment_date' in data and data['payment_date'] > timezone.now().date():
            raise serializers.ValidationError({
                "payment_date": "Payment date cannot be in the future."
            })
                  
        # Check for duplicate payments in the last 1 hour
        recent_time_1h = timezone.now() - timezone.timedelta(hours=1)
        duplicate_payments = Payment.objects.filter(
            invoice_id=data['invoice_id'],
            amount=data['amount'],
            created_at__gte=recent_time_1h
        ).exists()
        
        if duplicate_payments:
            raise serializers.ValidationError({
                "non_field_errors": "A payment with the same amount was recently recorded for this invoice. "
                                  "This might be a duplicate payment. Please confirm before proceeding."
            })
        
        # Check for any payments in the last 5 minutes
        recent_time_5m = timezone.now() - timezone.timedelta(minutes=5)
        recent_payments = Payment.objects.filter(
            invoice_id=data['invoice_id'],
            created_at__gte=recent_time_5m
        ).exists()
        
        if recent_payments:
            raise serializers.ValidationError({
                "non_field_errors": "A payment was recorded for this invoice in the last 5 minutes. "
                                  "Please wait before adding another payment."
            })
            
        return data
    
    @transaction.atomic
    def create(self, validated_data):
        invoice_id = validated_data.pop('invoice_id')
        invoice = Invoice.objects.select_related('client').get(id=invoice_id)
        
        # Set payment date to today if not provided
        if 'payment_date' not in validated_data:
            validated_data['payment_date'] = timezone.now().date()
        
        # All payments created through this serializer are manual and marked as COMPLETED
        payment = Payment.objects.create(
            invoice=invoice,
            client=invoice.client,
            status='COMPLETED',
            organization_id=invoice.organization_id,
            **validated_data
        )
        
        # Update invoice status after payment
        invoice.update_status_based_on_payments()
        
        return payment
    
    def to_representation(self, instance):
        return PaymentSerializer(instance).data


# ================================ Invoice Serializers ================================

class InvoiceSerializer(serializers.ModelSerializer):
    items = SimpleInvoiceItemSerializer(many=True, read_only=True)
    client = SimpleClientSerializer()
    days_overdue = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    tax_amount = serializers.SerializerMethodField()
    paid_amount = serializers.SerializerMethodField()
    due_balance = serializers.SerializerMethodField()
    payment_progress_percentage = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Invoice
        fields = [
            'id','client', 'invoice_number', 'issue_date',
            'due_date', 'status', 'tax_rate', 'notes', 'organization_name',
            'total_amount', 'tax_amount', 'paid_amount', 'due_balance', 'days_overdue',
            'late_fee_percentage', 'late_fee_applied', 'late_fee_amount',
            'payment_progress_percentage', 'allow_partial_payments',
            'minimum_payment_amount', 'items', 'uuid'
        ]
        
        

    def get_total_amount(self, obj):
        return obj.total_amount
    
    def get_tax_amount(self, obj):
        return obj.tax_amount
    
    def get_paid_amount(self, obj):
        return obj.paid_amount
    
    def get_due_balance(self, obj):
        return obj.due_balance
    
    def get_days_overdue(self, obj):
        return obj.days_overdue
    
    
    def get_payment_progress_percentage(self, obj):
        return obj.payment_progress_percentage
    
    def get_organization_name(self, obj):
        return obj.organization.name
    
    

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
        
        
# <>================================ Invoice Serializers =================================<>
class CreateInvoiceSerializer(serializers.ModelSerializer):
    items = CreateInvoiceItemSerializer(many=True)
    client_id = serializers.IntegerField()
    allow_partial_payments = serializers.BooleanField(required=True)
    minimum_payment_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    
    class Meta:
        model = Invoice
        fields = [
            'client_id', 'issue_date', 'due_date', 'tax_rate',
            'notes', 'items', 'late_fee_percentage', 'allow_partial_payments',
            'minimum_payment_amount'
        ]
    
    def validate_client_id(self, value):
        try:
            organization_id = self.context.get('organization_id')
            client = Client.objects.filter(
                id=value,
                organization_id=organization_id,
                status=Client.ACTIVE 
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
            
        # Calculate total invoice amount
        total_amount = Decimal('0')
        for item in data.get('items', []):
            quantity = Decimal(str(item['quantity']))
            unit_price = Decimal(str(item['unit_price']))
            total_amount += quantity * unit_price
        
        # Add tax if specified
        if 'tax_rate' in data:
            tax_rate = Decimal(str(data['tax_rate']))
            total_amount += total_amount * (tax_rate / Decimal('100'))
            
        # Validate partial payment settings
        allow_partial = data.get('allow_partial_payments', False)
        minimum_payment = data.get('minimum_payment_amount', Decimal('0.00'))
        
        if minimum_payment > total_amount:
            raise serializers.ValidationError({
                "minimum_payment_amount": "Minimum payment amount cannot be greater than the total invoice amount"
            })
        
        if allow_partial:
            if minimum_payment <= 0:
                raise serializers.ValidationError({
                    "minimum_payment_amount": "Minimum payment amount must be greater than 0 when partial payments are allowed"
                })
            if minimum_payment >= total_amount:
                raise serializers.ValidationError({
                    "minimum_payment_amount": "When partial payments are allowed, minimum payment amount must be less than the total invoice amount"
                })
        else:
            if minimum_payment > 0:
                raise serializers.ValidationError({
                    "minimum_payment_amount": "Minimum payment amount should be 0 when partial payments are not allowed"
                })
        
        # Validate late fee percentage
        late_fee = data.get('late_fee_percentage', Decimal('0.00'))
        if late_fee < 0 or late_fee > 100:
            raise serializers.ValidationError({
                "late_fee_percentage": "Late fee percentage must be between 0 and 100"
            })
            
        return data
    
    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        organization_id = self.context['organization_id']
        client_id = validated_data.pop('client_id')
        
        # Create invoice with organization and client
        invoice = Invoice.objects.create(
            organization_id=organization_id,
            client_id=client_id,
            status='DRAFT',  
            **validated_data
        )
        
        # Create all items
        for item_data in items_data:
            InvoiceItem.objects.create(invoice=invoice, **item_data)
        
        return invoice




# ================================ Invoice Serializers ================================     
class UpdateInvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, required=False)
    
    class Meta:
        model = Invoice
        fields = [
            'tax_rate', 'notes', 'items', 'late_fee_percentage', 
            'allow_partial_payments', 'minimum_payment_amount'
        ]
    
    def validate(self, data):
        # Check if invoice is in an editable state
        editable_states = ['DRAFT']
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
        
        # Validate partial payment settings
        allow_partial = data.get('allow_partial_payments')
        minimum_payment = data.get('minimum_payment_amount')
        
        # Only validate if either field is being updated
        if allow_partial is not None or minimum_payment is not None:
            # Use current values if not being updated
            if allow_partial is None:
                allow_partial = self.instance.allow_partial_payments
            if minimum_payment is None:
                minimum_payment = self.instance.minimum_payment_amount
            
            # If enabling partial payments, ensure minimum payment is set
            if allow_partial is True and minimum_payment <= 0:
                raise serializers.ValidationError({
                    "minimum_payment_amount": "When enabling partial payments, you must set a minimum payment amount greater than 0"
                })
            
            # If disabling partial payments, ensure minimum payment is 0
            if allow_partial is False and minimum_payment > 0:
                raise serializers.ValidationError({
                    "minimum_payment_amount": "When disabling partial payments, minimum payment amount must be set to 0"
                })
        
        # Validate late fee percentage
        if 'late_fee_percentage' in data:
            late_fee = data['late_fee_percentage']
            if late_fee < 0 or late_fee > 100:
                raise serializers.ValidationError({
                    "late_fee_percentage": "Late fee percentage must be between 0 and 100"
                })
        
        return data
    
    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        
        # Update invoice fields first
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Then handle items if provided
        if items_data is not None:
            # Delete existing items only if invoice is in DRAFT status
            if instance.status in ['DRAFT']:
                instance.items.all().delete()
                # Create new items
                for item_data in items_data:
                    InvoiceItem.objects.create(
                        invoice=instance,
                        product=item_data['product'],
                        description=item_data.get('description', ''),
                        quantity=item_data['quantity'],
                        unit_price=item_data['unit_price']
                    )
            else:
                raise serializers.ValidationError({
                    "items": "Cannot modify items for invoices not in DRAFT status"
                })
        
        return instance
        



class UpdatePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['payment_method', 'notes']
        read_only_fields = ['amount', 'payment_date', 'notes', 'transaction_id', 'status']
    
    def validate_payment_method(self, value):
        allowed_methods = ['CASH', 'BANK_TRANSFER', 'CHECK', 'WIRE_TRANSFER']
        if value not in allowed_methods:
            raise serializers.ValidationError(
                f"Only manual payment methods ({', '.join(allowed_methods)}) are allowed. "
                "Other payment types must be processed through their respective payment gateways."
            )
        return value
    
    def validate(self, data):
        # Get the current payment instance
        payment = self.instance
        
        # Define allowed manual payment methods
        allowed_methods = ['CASH', 'BANK_TRANSFER', 'CHECK', 'WIRE_TRANSFER']
        
        # Check if the original payment method is not a manual method
        if payment.payment_method not in allowed_methods:
            raise serializers.ValidationError({
                "error": f"Only payments made with manual payment methods ({', '.join(allowed_methods)}) can be modified. "
                "Other payment types must be processed through their respective payment gateways."
            })
        
        return data
    
    def update(self, instance, validated_data):
        with transaction.atomic():
            instance.payment_method = validated_data['payment_method']
            instance.notes = validated_data.get('notes', instance.notes)
            instance.save()
            
            return instance
        
        
# ================================ Bulk Invoice Item Serializers ================================
class BulkInvoiceItemSerializer(serializers.Serializer):
    items = CreateInvoiceItemSerializer(many=True)
    invoice_id = serializers.UUIDField()
    
    def validate_invoice_id(self, value):
        try:
            invoice = Invoice.objects.get(uuid=value)
            
            # Check if invoice is in an editable state
            if invoice.status not in ['DRAFT', 'PENDING']:
                raise serializers.ValidationError(
                    f"Cannot modify items for invoice in {invoice.status} status. "
                    "Only DRAFT or PENDING invoices can be modified."
                )
            
            return value
        except Invoice.DoesNotExist:
            raise serializers.ValidationError("Invalid invoice ID")
    
    def validate(self, data):
        # Ensure there's at least one item
        if not data.get('items'):
            raise serializers.ValidationError({
                "items": "Must provide at least one invoice item"
            })
        
        # Validate each item
        for item in data['items']:
            if item.get('quantity', 0) <= 0:
                raise serializers.ValidationError({
                    "items": "Item quantity must be greater than 0"
                })
            if item.get('unit_price', 0) < 0:
                raise serializers.ValidationError({
                    "items": "Item unit price cannot be negative"
                })
        
        return data
    
    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        invoice_id = validated_data.pop('invoice_id')
        
        invoice = Invoice.objects.get(uuid=invoice_id)
        created_items = []
        
        for item_data in items_data:
            item = InvoiceItem.objects.create(
                invoice=invoice,
                **item_data
            )
            created_items.append(item)
        
        return created_items
    
    def to_representation(self, instance):
        return {
            "detail": f"{len(instance)} invoice items created successfully",
            "items": InvoiceItemSerializer(instance, many=True).data
        }
        
        
# ================================ Recurring Invoice Item Serializers ================================
class RecurringInvoiceItemSerializer(serializers.ModelSerializer):
    amount = serializers.SerializerMethodField()
    
    class Meta:
        model = RecurringInvoiceItem
        fields = ['id', 'product', 'description', 'quantity', 'unit_price', 'amount']
        read_only_fields = ['amount']
    
    def get_amount(self, obj):
        return obj.amount
    
    def validate_quantity(self, value):
        if value <= Decimal('0'):
            raise serializers.ValidationError("Quantity must be greater than 0")
        return value
    
    def validate_unit_price(self, value):
        if value < Decimal('0'):
            raise serializers.ValidationError("Unit price cannot be negative")
        return value

class CreateRecurringInvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecurringInvoiceItem
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

# ================================ Recurring Invoice Serializers ================================
class RecurringInvoiceSerializer(serializers.ModelSerializer):
    items = RecurringInvoiceItemSerializer(many=True, read_only=True)
    client_name = serializers.CharField(source='client.name', read_only=True)
    
    class Meta:
        model = RecurringInvoice
        fields = [
            'uuid', 'client', 'client_name', 'title', 'frequency', 'status',
            'start_date', 'end_date', 'tax_rate', 'notes', 'next_generation_date',
            'payment_due_days', 'created_at', 'updated_at', 'items'
        ]
        read_only_fields = ['uuid', 'client_name', 'created_at', 'updated_at']

class CreateRecurringInvoiceSerializer(serializers.ModelSerializer):
    items = CreateRecurringInvoiceItemSerializer(many=True)
    client_id = serializers.IntegerField()
    
    class Meta:
        model = RecurringInvoice
        fields = [
            'client_id', 'title', 'frequency', 'start_date', 'end_date',
            'tax_rate', 'payment_due_days', 'notes', 'items'
        ]
    
    def validate_client_id(self, value):
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
    
    def validate_frequency(self, value):
        valid_frequencies = [choice[0] for choice in RecurringInvoice.FREQUENCY_CHOICES]
        if value not in valid_frequencies:
            raise serializers.ValidationError(f"Frequency must be one of: {', '.join(valid_frequencies)}")
        return value
    
    def validate(self, data):
        # Ensure start_date is not in the past
        if data.get('start_date') and data['start_date'] < timezone.now().date():
            raise serializers.ValidationError({
                "start_date": "Start date cannot be in the past"
            })
        
        # Check if end_date is after start_date
        if data.get('end_date') and data.get('start_date') and data['end_date'] <= data['start_date']:
            raise serializers.ValidationError({
                "end_date": "End date must be after start date"
            })
        
        # Ensure there's at least one item
        if not data.get('items'):
            raise serializers.ValidationError({
                "items": "Recurring invoice must have at least one item"
            })
            
        return data
    
    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        client_id = validated_data.pop('client_id')
        organization_id = self.context['organization_id']
        
        # Set the next_generation_date to the start_date initially
        validated_data['next_generation_date'] = validated_data['start_date']
        
        # Create recurring invoice
        recurring_invoice = RecurringInvoice.objects.create(
            client_id=client_id,
            organization_id=organization_id,
            **validated_data
        )
        
        # Create all items
        for item_data in items_data:
            RecurringInvoiceItem.objects.create(
                recurring_invoice=recurring_invoice,
                **item_data
            )
        
        return recurring_invoice

class UpdateRecurringInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecurringInvoice
        fields = ['title', 'frequency', 'status', 'end_date', 'tax_rate', 'payment_due_days', 'notes']
    
    def validate_frequency(self, value):
        valid_frequencies = [choice[0] for choice in RecurringInvoice.FREQUENCY_CHOICES]
        if value not in valid_frequencies:
            raise serializers.ValidationError(f"Frequency must be one of: {', '.join(valid_frequencies)}")
        return value
    
    def validate_status(self, value):
        valid_statuses = [choice[0] for choice in RecurringInvoice.FREQUENCY_CHOICES]
        if value not in valid_statuses:
            raise serializers.ValidationError(f"Status must be one of: {', '.join(valid_statuses)}")
        return value
    
    def validate_tax_rate(self, value):
        try:
            value = Decimal(str(value))
            if value < Decimal('0') or value > Decimal('100'):
                raise serializers.ValidationError("Tax rate must be between 0 and 100")
            return value
        except (TypeError, ValueError, DecimalException):
            raise serializers.ValidationError("Invalid decimal value")
    
    def validate(self, data):
        # Cannot modify a completed or cancelled recurring invoice
        if self.instance.status in ['COMPLETED', 'CANCELLED'] and 'status' not in data:
            raise serializers.ValidationError({
                "non_field_errors": f"Cannot modify a recurring invoice with {self.instance.status} status"
            })
        
        # Check if end_date is after start_date
        if data.get('end_date') and data['end_date'] <= self.instance.start_date:
            raise serializers.ValidationError({
                "end_date": "End date must be after start date"
            })
            
        return data
        
        