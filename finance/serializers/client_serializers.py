from rest_framework import serializers
from finance.models import Client, Address
from api.libs import validate_phone
from phonenumber_field.modelfields import PhoneNumberField
from django_countries.fields import CountryField


# <==============================> Simple Client Serializers <==========================================>

class SimpleClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['id', 'name', 'email', 'phone', 'status']



# <==============================>  Address Serializers <==========================================>

class AddressSerializer(serializers.ModelSerializer):
    country = CountryField()
    
    class Meta:
        model = Address
        fields = ['street', 'city', 'state', 'zip_code', 'country']
        
    def validate_street(self, value):
        if not value.strip():
            raise serializers.ValidationError("Street address cannot be empty")
        if len(value.strip()) < 5:
            raise serializers.ValidationError("Street address is too short")
        return value.strip()
    
    def validate_city(self, value):
        if not value.strip():
            raise serializers.ValidationError("City cannot be empty")
        if len(value.strip()) < 2:
            raise serializers.ValidationError("City name is too short")
        return value.strip()
    
    def validate_state(self, value):
        if not value.strip():
            raise serializers.ValidationError("State cannot be empty")
        if len(value.strip()) < 2:
            raise serializers.ValidationError("State name is too short")
        return value.strip()
    
    def validate_zip_code(self, value):
        if not value.strip():
            raise serializers.ValidationError("ZIP code cannot be empty")
        # Remove any spaces from zip code
        clean_zip = value.strip().replace(" ", "")
        if not clean_zip.isalnum():
            raise serializers.ValidationError("ZIP code can only contain letters and numbers")
        return clean_zip
    
    def validate_country(self, value):
        if not value.strip():
            raise serializers.ValidationError("Country cannot be empty")
        return value.strip()
        
    def validate(self, data):
        """Validate the entire address data"""
        # Check if all required fields are present
        required_fields = ['street', 'city', 'state', 'zip_code', 'country']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            error_dict = {field: "This field is required." for field in missing_fields}
            raise serializers.ValidationError(error_dict)
        return data
    
    
# <==============================>  Client Serializers <==========================================>

class ClientSerializer(serializers.ModelSerializer):
    total_paid = serializers.SerializerMethodField()
    total_outstanding = serializers.SerializerMethodField()
    address = AddressSerializer(read_only=True)  # Changed from addresses to address
    
    class Meta:
        model = Client
        fields = [
            'id', 'name', 'email', 'phone', 
            'tax_number', 'status', 'total_outstanding', 'total_paid',
            'address'  
        ]
        read_only_fields = ['created_at']
    
    def get_total_paid(self, obj):
        return obj.total_paid
    
    def get_total_outstanding(self, obj):
        return obj.total_outstanding
    


# <==============================>  Create Client Serializers <==========================================>

class CreateClientSerializer(serializers.ModelSerializer):
    phone = PhoneNumberField(validators=[validate_phone.validate_phone])
    id = serializers.IntegerField(read_only=True)
    address = AddressSerializer() 
    
    class Meta:
        model = Client
        fields = ['id', 'name', 'email', 'phone', 'tax_number', 'status', 'address']
        
    def validate_email(self, value):
        if value and Client.objects.filter(email=value).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError("This email is already in use")
        return value
    
    def validate(self, data):
        """Validate the entire data dictionary"""
        # Check if client name already exists
        if Client.objects.filter(
            name__iexact=data.get('name'), 
            organization=self.context['organization_id']
        ).exists():
            raise serializers.ValidationError({"name": "This name is already in use"})
        return data

    def create(self, validated_data):
        address_data = validated_data.pop('address')
        
        # Add organization to validated data
        organization_id = self.context['organization_id']
        validated_data['organization_id'] = organization_id
        
        # Create the client
        client = super().create(validated_data)
        
        # Create address
        Address.objects.create(client=client, **address_data)
        
        return client

    def to_representation(self, instance):
        """
        Override to_representation to include the address in the response
        """
        representation = super().to_representation(instance)
        if hasattr(instance, 'address'):
            representation['address'] = AddressSerializer(instance.address).data
        return representation


# <==============================>  Update Client Serializers <==========================================>

class UpdateClientSerializer(serializers.ModelSerializer):
    address = AddressSerializer(required=False)
    
    class Meta:
        model = Client
        fields = ['id', 'name', 'email', 'phone', 'tax_number', 'status', 'address']
    
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
    
    def update(self, instance, validated_data):
        # Extract address data if present
        address_data = validated_data.pop('address', None)
        
        # Update client fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update or create address if provided
        if address_data:
            if hasattr(instance, 'address') and instance.address:
                # Update existing address
                address = instance.address
                for attr, value in address_data.items():
                    setattr(address, attr, value)
                address.save()
            else:
                # Create new address
                Address.objects.create(client=instance, **address_data)
        
        return instance


    


    