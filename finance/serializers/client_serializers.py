from rest_framework import serializers
from finance.models import Client
from api.libs import validate_phone
from phonenumber_field.modelfields import PhoneNumberField

class ClientSerializer(serializers.ModelSerializer):
    total_paid = serializers.SerializerMethodField()
    total_outstanding = serializers.SerializerMethodField()
    
    class Meta:
        model = Client
        fields = [
            'id', 'name', 'email', 'phone', 
            'tax_number', 'status', 'total_outstanding', 'total_paid', 
        ]
        read_only_fields = ['created_at']
    
    def get_total_paid(self, obj):
        return obj.total_paid
    
    def get_total_outstanding(self, obj):
        return obj.total_outstanding
    

# <================================> Client Serializers <==========================================>

class CreateClientSerializer(serializers.ModelSerializer):
    phone  =  PhoneNumberField(validators=[validate_phone.validate_phone])
    id = serializers.IntegerField(read_only=True)
    class Meta:
        model = Client
        fields = ['id', 'name', 'email', 'phone', 'tax_number', 'status']
        
    
    def validate_email(self, value):
        if value and Client.objects.filter(email=value).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError("This email is already in use")
        return value

    
    def create(self, validated_data):
        if Client.objects.filter(name__iexact=validated_data.get('name'), organization=self.context['organization_id']).exists():
            raise serializers.ValidationError("This name is already in use")
        organization_id = self.context['organization_id']
        validated_data['organization_id'] = organization_id
        return super().create(validated_data)
    
    


class UpdateClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['id', 'name', 'email', 'phone', 'tax_number', 'status']
    
    def validate_email(self, value):
        if value and Client.objects.filter(email=value, organization=self.instance.organization).exclude(id=self.instance.id).exists():
            raise serializers.ValidationError("This email is already in use")
        return value
    
    def validate_name(self, value):
        if value and Client.objects.filter(name__iexact=value, organization=self.instance.organization).exclude(id=self.instance.id).exists():
            raise serializers.ValidationError("This name is already in use")
        return value
    
    def validate_phone(self, value):
        if value and Client.objects.filter(phone=value, organization=self.instance.organization).exclude(id=self.instance.id).exists():
            raise serializers.ValidationError("This phone number is already in use")
        return value


    

