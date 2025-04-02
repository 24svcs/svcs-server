from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated
from rest_framework import  filters
from core.pagination import DefaultPagination



import pytz
from core.serializers import(
    Permission,
    User,
    Language,
    LanguageSerializer, 
    PermissionSerializer,
    UserSerializer,
    AcceptInvitationSerializer,
    RejectInvitationSerializer,
    InvitationSerializer,
    Invitation
)
from core.mixins import TimezoneMixin
from rest_framework import mixins
from django.db import models
class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    pagination_class = DefaultPagination
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer

    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    def update_user_timezone(request):
        """
        Update the authenticated user's timezone preference
        """
        timezone_str = request.data.get('timezone')
        
        if not timezone_str:
            return Response(
                {"error": "Timezone is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate the timezone
        try:
            pytz.timezone(timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            return Response(
                {"error": f"Invalid timezone: {timezone_str}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update the user's timezone
        request.user.timezone = timezone_str
        request.user.save()
        
        return Response({"timezone": timezone_str}, status=status.HTTP_200_OK)
    

    
class LanguageViewSet(viewsets.ReadOnlyModelViewSet):
    pagination_class = DefaultPagination
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['code__exact', 'name__istartwith']
    serializer_class = PermissionSerializer
    queryset = Language.objects.all().order_by('code')
    serializer_class = LanguageSerializer


class UserViewSet(
    viewsets.GenericViewSet,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin):
    
    """
    API endpoint for users with optimized queries.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer
    
    
    def get_queryset(self):
        return User.objects.filter(id=self.request.user.id)
    
    


class UserInvitationViewSet(TimezoneMixin,
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin
):
    pagination_class = DefaultPagination
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['organization__name__istartswith', 'organization__email__istartswith']
    
    def get_serializer_class(self):
        if self.action == 'accept':
            return AcceptInvitationSerializer
        elif self.action == 'reject':
            return RejectInvitationSerializer
        return InvitationSerializer
    
    def get_queryset(self):
        return Invitation.objects.filter(
            email=self.request.user.email
        ).select_related('organization', 'invited_by')
    
    @action(detail=True, methods=['post'], url_path='accept')
    def accept(self, request, user_pk=None, pk=None):
        """
        Accept an invitation to join an organization
        """
        invitation = self.get_object()
        serializer = self.get_serializer(invitation, data={}, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, user_pk=None, pk=None):
        """
        Reject an invitation to join an organization
        """
        invitation = self.get_object()
        serializer = self.get_serializer(invitation, data={}, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def get_serializer_context(self):
        # Get the context from the parent class (including timezone)
        context = super().get_serializer_context()
        # Add your custom context
        context['email'] = self.request.user.email
        return context
    
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            stats = Invitation.objects.filter(email=self.request.user.email).aggregate(
                total_invitations=models.Count('id'),
                pending_invitations=models.Count('id', filter=models.Q(status=Invitation.PENDING)),
                accepted_invitations=models.Count('id', filter=models.Q(status=Invitation.ACCEPTED)),
                rejected_invitations=models.Count('id', filter=models.Q(status=Invitation.REJECTED))
            )
            
            response.data['statistics'] = stats
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    
    
    