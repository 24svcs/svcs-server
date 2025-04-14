from rest_framework import serializers
from finance.models import  Invoice, InvoiceItem



# ================================ Invoice Item Serializers ================================
class SimpleInvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ['id', 'product', 'unit_price', 'quantity']



# ================================ Invoice Serializers ================================

class SimpleInvoiceSerializer(serializers.ModelSerializer):
    client = serializers.SerializerMethodField()
    due_balance = serializers.SerializerMethodField()
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'client', 'invoice_number', 'status', 'due_balance'
        ]
        
        
    def get_client(self, obj):
        return obj.client.name

    def get_due_balance(self, obj):
        return obj.due_balance
    
    
    
