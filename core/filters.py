from django_filters.rest_framework import FilterSet
from organization.models import MemberInvitation


class InvitationFilter(FilterSet):
    class Meta:
        model = MemberInvitation
        fields = {
            'status': ['exact'],
        }
