from rest_framework import serializers

from django.utils import timezone
from django.db import transaction
from core.serializers import SimpleUserSerializer, SimplePermissionSerializer
from organization.models import Member, MemberInvitation
import pytz
from django.utils import timezone as tz
from api.libs.tz import convert_datetime_to_timezone
from api.libs.validate_email import validate_email_invitation


class MemberSerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer(read_only=True)
    permissions = SimplePermissionSerializer(many=True, read_only=True)
    
    
    class Meta:
        model = Member
        fields = [
            'id', 'user',
            'is_owner', 'is_admin', 'status',
            'joined_at', 'last_active_at', 'permissions'
        ]
        
    def validate_status(self, value):
        if value not in [Member.ACTIVE, Member.INACTIVE]:
            raise serializers.ValidationError("Invalid status")
        return value
    
    
    
class UpdateMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Member
        fields = ['status', 'is_admin', 'permissions']
        
    def validate_status(self, value):
        if value not in [Member.ACTIVE, Member.INACTIVE]:
            raise serializers.ValidationError("Invalid status")
        return value
        
    def validate(self, attrs):
        # Only prevent is_owner modification, allow other field updates
        if 'is_owner' in attrs:
            raise serializers.ValidationError(
                "The ownership status cannot be modified through this endpoint."
            )
            
        return attrs
            
    def update(self, instance, validated_data):
        # Remove is_owner from validated_data if it exists
        validated_data.pop('is_owner', None)
        return super().update(instance, validated_data)

    
class InvitedMemberSerializer(serializers.ModelSerializer):
    invited_by = SimpleUserSerializer(read_only=True)
    class Meta:
        model = MemberInvitation
        fields = ['id', 'email', 'message', 'invited_at', 'status', 'invited_by']
        
        
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
                # Use the utility function for conversion
                converted_dt = convert_datetime_to_timezone(dt, timezone)
                # Format back to ISO 8601
                representation[field] = converted_dt.isoformat()
        
        return representation
        

class CreateInviteMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = MemberInvitation
        fields = ['name','email', 'message']
    
    def validate_email(self, value):
        organization_id = self.context['organization_id']
        return validate_email_invitation(value, organization_id)
    
    def create(self, validated_data):
        organization_id = self.context['organization_id']
        validated_data['organization_id'] = organization_id
        validated_data['invited_by'] = self.context['request'].user
        return super().create(validated_data)
    

class UpdateInviteMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = MemberInvitation
        fields = ['status', 'is_updated']
        
    def validate(self, attrs):
        if not self.instance:
            raise serializers.ValidationError('Invalid invitation.')
            
        # Existing validation checks
        if self.instance.status != MemberInvitation.PENDING:
            raise serializers.ValidationError(
                f'This invitation is no longer valid. Current status: {self.instance.get_status_display()}'
            )
            
        if self.instance.is_updated:
            raise serializers.ValidationError('This invitation has already been processed.')
            
        return super().validate(attrs)

    def update(self, instance, validated_data):
        new_status = validated_data.get('status')
        current_user = self.context['request'].user
        
        # Check if user is authenticated
        if not current_user.is_authenticated:
            raise serializers.ValidationError('You must be logged in to accept invitations.')
        
        # Verify email case-insensitively and after stripping whitespace
        if current_user.email.lower().strip() != instance.email.lower().strip():
            raise serializers.ValidationError(
                'You cannot accept an invitation that was sent to a different email address.'
            )
        
        # Check if  organization still exists
        try:
            organization = instance.organization
        except organization.DoesNotExist:
            instance.delete()
            raise serializers.ValidationError('The organization associated with this invitation no longer exists.')
        
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
                if new_status == MemberInvitation.ACCEPTED:
                    Member.objects.create(
                        organization=instance.organization,
                        user=current_user,
                        status=Member.ACTIVE,
                        joined_at=timezone.now()
                    )
                
                instance.status = new_status
                instance.is_updated = True
                instance.save()
                
                return instance
                
            except Exception as e:
                raise serializers.ValidationError(
                    f'Error processing invitation: {str(e)}'
                )





