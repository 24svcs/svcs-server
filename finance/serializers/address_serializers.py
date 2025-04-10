from rest_framework import serializers
from finance.models import Address
from django_countries.fields import CountryField


class AddressSerializer(serializers.ModelSerializer):
    client = serializers.SerializerMethodField()    

    class Meta:
        model = Address
        fields = ['id', 'street', 'city', 'state', 'zip_code', 'country', 'client_id']
        
    

class CreateAddressSerializer(serializers.ModelSerializer):
    country = CountryField()

    class Meta:
        model = Address
        fields = ['street', 'city', 'state', 'zip_code', 'country', 'client_id']



class UpdateAddressSerializer(serializers.ModelSerializer):
    country = CountryField()

    class Meta:
        model = Address
        fields = ['street', 'city', 'state', 'zip_code', 'country']
