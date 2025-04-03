from rest_framework import serializers
from core.serializers import SimpleUserSerializer, SimplePermissionSerializer
from organization.models import Member, Invitation, Organization
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

    
class InvitationSerializer(serializers.ModelSerializer):
    inviter_name = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Invitation
        fields = ['id', 'name', 'email', 'message', 'invited_at', 'status', 'inviter_name', 'organization_name']
    
    def get_inviter_name(self, obj):
        if obj.invited_by:
            return f"{obj.invited_by.first_name} {obj.invited_by.last_name}".strip()
        return ""
        
    def get_organization_name(self, obj):
        if obj.organization:
            return obj.organization.name
        return ""
        
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
        

class CreateInvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invitation
        fields = ['name','email', 'message']
    
    def validate_email(self, value):
        organization_id = self.context['organization_id']
        return validate_email_invitation(value, organization_id)
    
    def validate(self, attrs):
        organization_id = self.context['organization_id']
        
        # Check if organization exists
        try:
            organization = Organization.objects.get(id=organization_id)
        except Organization.DoesNotExist:
            raise serializers.ValidationError('The organization does not exist.')
            
        # Check organization member limit
        current_member_count = organization.members.count()
        member_limit = organization.get_member_limit()
        
        if current_member_count >= member_limit:
            raise serializers.ValidationError(
                f'This organization has reached its member limit of {member_limit} members.'
            )
            
        # Check if user is already a member
        email = attrs.get('email')
        if Member.objects.filter(organization=organization, user__email=email).exists():
            raise serializers.ValidationError(
                'This user is already a member of this organization.'
            )
            
        # Check if there's already a pending invitation for this email
        if Invitation.objects.filter(
            organization=organization,
            email=email,
            status=Invitation.PENDING
        ).exists():
            raise serializers.ValidationError(
                'An invitation has already been sent to this email address.'
            )
            
        return attrs
    
    def create(self, validated_data):
        organization_id = self.context['organization_id']
        validated_data['organization_id'] = organization_id
        validated_data['invited_by'] = self.context['request'].user
        return super().create(validated_data)
    
    def to_representation(self, instance):
        """
        Convert the invitation instance to a flatter response structure
        """
        data = super().to_representation(instance)
        
        # Add flattened data
        data.update({
            'invitation_id': instance.id,
            'organization_id': instance.organization.id,
            'organization_name': instance.organization.name,
            'sender_name': f"{instance.invited_by.first_name} {instance.invited_by.last_name}".strip(),
            'status': instance.status,
            'invited_at': instance.invited_at.isoformat() if instance.invited_at else None,
            'response_link': f"{instance.id}"
        })
        
        return data
