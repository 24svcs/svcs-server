
from rest_framework import serializers
from .models import Permission
from .models import User
from .models import Language

class SimpleUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email', 'username', 'first_name', 'last_name','image_url']


class PermissionSerializer(serializers.ModelSerializer):
    name_display = serializers.CharField(source='get_name_display', read_only=True)

    class Meta:
        model = Permission
        fields = ['id', 'name', 'name_display', 'category']
        

class SimplePermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ['id','name']    
        
        
class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Language
        fields = ['id','code', 'name']
