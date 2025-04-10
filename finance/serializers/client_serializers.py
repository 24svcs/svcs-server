from rest_framework import serializers
from finance.models import Client
from api.libs import validate_phone
from phonenumber_field.modelfields import PhoneNumberField

class ClientSerializer(serializers.ModelSerializer):
    total_paid = serializers.SerializerMethodField()
    total_outstanding = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    
    class Meta:
        model = Client
        fields = [
            'id', 'name', 'email', 'phone', 
            'tax_number', 'is_active', 'total_outstanding', 'total_paid', 'address'
        ]
        read_only_fields = ['created_at']
    
    def get_total_paid(self, obj):
        return obj.total_paid
    
    def get_total_outstanding(self, obj):
        return obj.total_outstanding
    
    def get_address(self, obj):
        if hasattr(obj, '_prefetched_objects_cache') and 'addresses' in obj._prefetched_objects_cache:
            addresses = obj._prefetched_objects_cache['addresses']
            if addresses:
                address = addresses[0]  # Get the first address
                return f"{address.street}, {address.city}, {address.state} {address.zip_code}, {address.country}"
        return None


# <================================> Client Serializers <==========================================>

class CreateClientSerializer(serializers.ModelSerializer):
    phone  =  PhoneNumberField(validators=[validate_phone.validate_phone])
    id = serializers.IntegerField(read_only=True)
    class Meta:
        model = Client
        fields = ['id', 'name', 'email', 'phone', 'tax_number', 'is_active']
        
    
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
    
    
    def update(self, instance, validated_data):
        if Client.objects.filter(name__iexact=validated_data.get('name'), organization=self.context['organization_id']).exclude(id=instance.id).exists():
            raise serializers.ValidationError("This name is already in use")
        
        instance.name = validated_data.get('name', instance.name)
        instance.email = validated_data.get('email', instance.email)
        instance.phone = validated_data.get('phone', instance.phone)
        instance.tax_number = validated_data.get('tax_number', instance.tax_number)
        instance.is_active = validated_data.get('is_active', instance.is_active)
        instance.save()
        return instance
    

    

