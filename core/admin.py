from django.contrib import admin
from .models import User, Permission, Language

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('id', 'email', 'first_name', 'last_name', 'username', 'timezone')
    search_fields = ('id', 'email', 'first_name', 'last_name', 'username')
    
    search_fields = ('id', 'email', 'first_name', 'last_name', 'username', 'timezone')
    
    
@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ('id' ,'name')
    search_fields = ('id', 'name')
    
    
@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ['id', 'code', 'name']