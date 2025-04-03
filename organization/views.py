from django.db import transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import mixins
from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from django.utils.translation import gettext_lazy as _
from organization.serializers.organization import(
    SimpleOrganizationSerializer,
    Organization,
    UpdateOrganizationSerializer,
    CreateOrganizationSerializer,
    OrganizationSerializer,
    RestoreOrganizationSerializer,
    TransferOwnershipSerializer
)
from core.mixins import TimezoneMixin
from organization.models import Member
from core.models import Permission
from core.pagination import DefaultPagination
from api.permission import OrganizationPermission
from organization.filters import OrganizationFilter
from organization.serializers.member import (
    MemberSerializer,
    UpdateMemberSerializer,
    CreateInvitationSerializer,
    InvitationSerializer,
    Invitation
)

from organization.filters import MemberFilter, InvitationFilter
from django.db import models


class OrganizationViewSet(TimezoneMixin, viewsets.ModelViewSet):
    """
    API endpoint for companies with optimized queries.
    """
    pagination_class = DefaultPagination
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['name__istartwith', 'email__iexact']
    filterset_class = OrganizationFilter 
    
    def get_queryset(self):
        user = self.request.user
        
        if self.action == 'list':
            return Organization.objects.filter(
                members__user=user,
                members__status=Member.ACTIVE,
            ).only(
                'id', 'name', 'name_space', 'email', 'logo_url'
            ).distinct()
        else:
            return Organization.objects.prefetch_related(
                # 'members__permissions',
            ).select_related(

            ).filter(
                members__user=user,
                members__status=Member.ACTIVE,
            ).distinct().order_by('name')


    
    def get_permissions(self):
        if self.action in ['update', 'partial_update']:
            return [IsAuthenticated(), OrganizationPermission(Permission.EDIT_ORGANIZATION)]
        elif self.action == 'destroy':
            return [IsAuthenticated(), OrganizationPermission(Permission.DELETE_ORGANIZATION)]
        return [IsAuthenticated()]



    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return UpdateOrganizationSerializer
        elif self.action == 'list':
            return SimpleOrganizationSerializer
        elif self.action == 'create':
            return CreateOrganizationSerializer
        return OrganizationSerializer
    
    
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['user_id'] = self.request.user.id
        return context
    
    
    @action(detail=False, methods=['GET'], url_name='me')
    def my_organization(self, request, pk=None):
        user_id = self.request.user.id
        
        organization = Organization.objects.filter(
            user_id=user_id,
        ).first()
        
        if not organization:
            return Response({'detail': 'No organization found'}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = self.get_serializer(organization)
        return Response(serializer.data)
    

    @action(detail=True, methods=['post'], url_path='transfer-ownership', permission_classes=[IsAuthenticated])
    def transfer_ownership(self, request, pk=None):
        organization = self.get_object()

        # Verify current user is the owner
        try:
            member = Member.objects.get(
                organization=organization,
                user=request.user,
                is_owner=True
            )
        except Member.DoesNotExist:
            return Response(
                {'detail': _('Only the organization owner can transfer ownership.')},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = TransferOwnershipSerializer(data=request.data)
        if serializer.is_valid():
            try:
                serializer.transfer_ownership(organization)
                return Response(
                    {'detail': _('Ownership transferred successfully.')},
                    status=status.HTTP_200_OK
                )
            except Exception as e:
                return Response(
                    {'detail': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=False, methods=['post'], url_path='restore', permission_classes=[IsAuthenticated])
    def restore_organization(self, request):
        """
        Restore a soft-deleted organization.
        Only the original owner can restore an organization.
        """
        serializer = RestoreOrganizationSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    organization = serializer.restore_organization()
                    
                    # Reactivate the owner's membership if it was deactivated
                    Member.objects.filter(
                        organization=organization,
                        user=request.user,
                        is_owner=True
                    ).update(status=Member.ACTIVE)
                    
                    return Response(
                        {'detail': _('Organization restored successfully.'),
                         'id': organization.id},
                        status=status.HTTP_200_OK
                    )
            except Exception as e:
                return Response(
                    {'detail': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['GET'], url_path='owner')
    def owner(self, request, pk=None):
        """
        Returns the organization where the current user is the owner.
        """
        user_id = self.request.user.id
        
        organization = Organization.objects.filter(
            members__user_id=user_id,
            members__is_owner=True,
            members__status=Member.ACTIVE,
        ).first()
        
        if not organization:
            return Response({'detail': 'You are not an owner of any organization'}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = self.get_serializer(organization)
        return Response(serializer.data)



# ===================== Members Viewset =====================
class MemberViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin
):
    """
    API endpoint for members with optimized queries.
    """
    pagination_class = DefaultPagination
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['user__email', 'user__first_name', 'user__last_name']
    filterset_class = MemberFilter
    
    def get_permissions(self):
        if self.action in ['update', 'partial_update']:
            return [IsAuthenticated(), OrganizationPermission(Permission.EDIT_ORGANIZATION_MEMBER)]
        elif self.action == 'destroy':
            return [IsAuthenticated(), OrganizationPermission(Permission.DELETE_ORGANIZATION_MEMBER)]
        return [IsAuthenticated()]
    
    
    def get_serializer_class(self):
        if self.request.method in ['PATCH', 'PUT']:
            return UpdateMemberSerializer
        return MemberSerializer
    
    def get_queryset(self):
        return Member.objects.select_related('organization', 'user').prefetch_related('permissions').filter(
            organization_id=self.kwargs['organization_pk']
        ).order_by('user__first_name', 'user__last_name')
    
    def get_serializer_context(self):
        return {'organization_id': self.kwargs['organization_pk']}
    
    def get_filterset_kwargs(self):
        kwargs = super().get_filterset_kwargs()
        kwargs['request'] = self.request
        return kwargs
    
    def perform_update(self, serializer):
        instance = serializer.instance
        
        # Prevent updating owner membership
        if instance.is_owner:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Owner membership cannot be modified.")
        serializer.save()
    
    
    def perform_destroy(self, instance):
        # Check if the member is the owner
        if instance.is_owner:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Cannot delete the Organization owner's membership.")
            
        # with transaction.atomic():
        #     # Delete associated invitation if it exists
        #     MemberInvitation.objects.filter(
        #         organization=instance.organization,
        #         email__iexact=instance.user.email
        #     ).delete()
            
            # Delete the member
            return super().perform_destroy(instance)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            stats = Member.objects.select_related('organization').filter(organization_id=self.kwargs['organization_pk']).aggregate(
                total_members=models.Count('id'),
                active_members=models.Count('id', filter=models.Q(status=Member.ACTIVE)),
                inactive_members=models.Count('id', filter=models.Q(status=Member.INACTIVE))
            )
            
            response.data['statistics'] = stats
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


# ===================== Member Invitation Viewset =====================


class InvitationViewSet(
    TimezoneMixin,
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin
):
    pagination_class = DefaultPagination
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['email__istartswith', 'invited_by__first_name__istartswith', 'invited_by__last_name__istartswith']
    filterset_class = InvitationFilter
    
    def get_queryset(self):
        return Invitation.objects.filter(
            organization_id=self.kwargs['organization_pk']
        ).select_related('organization', 'invited_by')
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return  CreateInvitationSerializer
        return InvitationSerializer
    
    def perform_destroy(self, instance):
        if instance.status != Invitation.PENDING:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Only pending invitations can be deleted.")
        return super().perform_destroy(instance)
    
    
    def get_serializer_context(self):
        # Get the context from the parent class (including timezone)
        context = super().get_serializer_context()
        # Add your custom context
        context['organization_id'] = self.kwargs['organization_pk']
        return context
    
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            stats = Invitation.objects.filter(organization_id=self.kwargs['organization_pk']).aggregate(
                total_invitations=models.Count('id'),
                pending_invitations=models.Count('id', filter=models.Q(status=Invitation.PENDING)),
                accepted_invitations=models.Count('id', filter=models.Q(status=Invitation.ACCEPTED)),
                rejected_invitations=models.Count('id', filter=models.Q(status=Invitation.REJECTED))
            )
            
            response.data['statistics'] = stats
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    
    
    
