from rest_framework import serializers
from .models import Permission, User, Language
from organization.models import  Invitation, Member
from django.utils import timezone
from django.db import transaction
import pytz
from django.utils import timezone as tz
from api.libs.tz import convert_datetime_to_timezone
from django.core.exceptions import ValidationError


class SimpleUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email', 'username', 'first_name', 'last_name','image_url']


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name','image_url']
        
        
        

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



# ===============================
# Invitation Serializer
# ===============================

class InvitationSerializer(serializers.ModelSerializer):
    invited_by = SimpleUserSerializer(read_only=True)
    class Meta:
        model = Invitation
        fields = ['id', 'name', 'email', 'message', 'invited_at', 'status', 'invited_by']
        
        
    def to_representation(self, instance):
        """
        Convert datetime fields to the requested timezone
        """
        representation = super().to_representation(instance)
        
        # Get timezone from context (set by TimezoneMixin)
        timezone = self.context.get('timezone', pytz.UTC)
        
        # Convert datetime fields
        datetime_fields = ['invited_at']
        for field in datetime_fields:
            if representation.get(field):
                # Parse the datetime string
                dt = tz.datetime.fromisoformat(representation[field].replace('Z', '+00:00'))
                converted_dt = convert_datetime_to_timezone(dt, timezone)
                # Format back to ISO 8601
                representation[field] = converted_dt.isoformat()
        
        return representation
        


# # ===============================
# # Accept Invitation Serializer
# # ===============================

class AcceptInvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invitation
        fields = []  # We don't need any fields since we'll hardcode the status
        
    def validate(self, attrs):
        if not self.instance:
            raise serializers.ValidationError('Invalid invitation.')
            
        # Check if invitation has expired
        if self.instance.is_expired():
            raise serializers.ValidationError('This invitation has expired.')
            
        # Existing validation checks
        if self.instance.status != Invitation.PENDING:
            raise serializers.ValidationError(
                f'This invitation is no longer valid. Current status: {self.instance.get_status_display()}'
            )
            
        if self.instance.is_updated:
            raise serializers.ValidationError('This invitation has already been processed.')
            
        # Check organization member limit before proceeding
        try:
            organization = self.instance.organization
            current_member_count = organization.members.count()
            member_limit = organization.get_member_limit()
            
            if current_member_count >= member_limit:
                raise serializers.ValidationError(
                    f'This organization has reached its member limit of {member_limit} members.'
                )
        except organization.DoesNotExist:
            raise serializers.ValidationError('The organization associated with this invitation no longer exists.')
            
        return super().validate(attrs)

    def update(self, instance, validated_data):
        current_user = self.context['request'].user
        
        # Check if user is authenticated
        if not current_user.is_authenticated:
            raise serializers.ValidationError('You must be logged in to accept invitations.')
        
        # Verify email case-insensitively and after stripping whitespace
        if current_user.email.lower().strip() != instance.email.lower().strip():
            raise serializers.ValidationError(
                'You cannot accept an invitation that was sent to a different email address.'
            )
        
        # Check if user is already a member
        existing_member = Member.objects.filter(
            organization=instance.organization,
            user=current_user
        ).first()
        
        if existing_member:
            instance.delete()
            raise serializers.ValidationError(
                'You are already a member of this organization. Invitation has been removed.'
            )
        
        # Process the actual acceptance in a transaction
        with transaction.atomic():
            try:
                # Create member with clean() to validate member limit again (double-check)
                member = Member(
                    organization=instance.organization,
                    user=current_user,
                    status=Member.ACTIVE,
                    joined_at=timezone.now()
                )
                member.clean()  # This will raise ValidationError if limit is reached
                member.save()
                
                instance.status = Invitation.ACCEPTED
                instance.is_updated = True
                instance.save()
                
                return instance
                
            except ValidationError as e:
                raise serializers.ValidationError(str(e))
            except Exception as e:
                raise serializers.ValidationError(
                    f'Error processing invitation: {str(e)}'
                )



# ===============================
# Reject Invitation Serializer
# ===============================

class RejectInvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invitation
        fields = []  # We don't need any fields since we'll hardcode the status
        
    def validate(self, attrs):
        if not self.instance:
            raise serializers.ValidationError('Invalid invitation.')
            
        # Check if invitation has expired
        if self.instance.is_expired():
            raise serializers.ValidationError('This invitation has expired.')
            
        # Existing validation checks
        if self.instance.status != Invitation.PENDING:
            raise serializers.ValidationError(
                f'This invitation is no longer valid. Current status: {self.instance.get_status_display()}'
            )
            
        if self.instance.is_updated:
            raise serializers.ValidationError('This invitation has already been processed.')
            
        return super().validate(attrs)

    def update(self, instance, validated_data):
        current_user = self.context['request'].user
        
        # Check if user is authenticated
        if not current_user.is_authenticated:
            raise serializers.ValidationError('You must be logged in to reject invitations.')
        
        # Verify email case-insensitively and after stripping whitespace
        if current_user.email.lower().strip() != instance.email.lower().strip():
            raise serializers.ValidationError(
                'You cannot reject an invitation that was sent to a different email address.'
            )
        
        # Check if organization still exists
        try:
            organization = instance.organization
        except organization.DoesNotExist:
            instance.delete()
            raise serializers.ValidationError('The organization associated with this invitation no longer exists.')
        
        # Process the rejection in a transaction
        with transaction.atomic():
            try:
                instance.status = Invitation.REJECTED
                instance.is_updated = True
                instance.save()
                
                return instance
                
            except Exception as e:
                raise serializers.ValidationError(
                    f'Error processing invitation rejection: {str(e)}'
                )
        
        
        