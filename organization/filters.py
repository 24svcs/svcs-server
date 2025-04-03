from django_filters.rest_framework import FilterSet
from .models import Organization, Member, Invitation

class OrganizationFilter(FilterSet):
    class Meta:
        model = Organization
        fields = {
            'is_verified': ['exact'],
        }
        



class MemberFilter(FilterSet):
    class Meta:
        model = Member
        fields = {
            'status': ['exact'],
        }


class InvitationFilter(FilterSet):
    class Meta:
        model = Invitation
        fields = {
            'status': ['exact'],
            'invited_at': ['gte', 'lte'],
        }
