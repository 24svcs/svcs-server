from django.contrib import admin
from .models import Organization, Preference, Member

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'name_space', 'email', 'phone', 'tax_id', 'logo', 'currency')
    search_fields = ('id', 'name', 'name_space', 'email', 'phone', 'tax_id', 'logo', 'currency')


@admin.register(Preference)
class OrganizationPreferencesAdmin(admin.ModelAdmin):
    list_display = ('id', 'theme', 'timezone', 'language')




@admin.register(Member)
class OrganizationMemberAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'organization', 'status')
    search_fields = ('id', 'user__email', 'organization__name')

