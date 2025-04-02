from email_validator import validate_email as email_validator, EmailNotValidError
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from organization.models import Organization, Invitation

def check_disposable_email_domain(normalized_email):
    disposable_domains = {
        'tempmail.com', 'throwawaymail.com', 'mailinator.com', 
        'guerrillamail.com', 'sharklasers.com', 'yopmail.com',
        'temp-mail.org', '10minutemail.com', 'trashmail.com',
    }
    domain = normalized_email.split('@')[1]
    if domain.lower() in disposable_domains:
        raise serializers.ValidationError(_('Please use a permanent email address. Disposable email addresses are not allowed.'))

def check_email_uniqueness(normalized_email, instance=None):
    query = Organization.objects.filter(email__iexact=normalized_email)
    if instance:
        query = query.exclude(id=instance.id)
    if query.exists():
        raise serializers.ValidationError(_('A organization with this email already exists.'))

def validate_organization_email(value, instance=None):
    """
    Validates organization email format and business rules.
    """
    try:
        validation = email_validator(value, check_deliverability=True)
        normalized_email = validation.normalized.lower()  # Normalize to lowercase
        
        check_email_uniqueness(normalized_email, instance)
        check_disposable_email_domain(normalized_email)
        
        return normalized_email
        
    except EmailNotValidError as e:
        raise serializers.ValidationError(str(e))


def validate_email_invitation(value, organization_id, instance=None):
    """
    Validates organization email format and business rules.
    Ensures the same organization cannot send multiple invitations to the same email
    if the first invitation is pending or accepted.
    """
    try:
        validation = email_validator(value, check_deliverability=True)
        normalized_email = validation.normalized.lower()  # Normalize to lowercase
        
        check_email_uniqueness(normalized_email, instance)
        check_disposable_email_domain(normalized_email)
        
        # Check for existing invitation with same email for the same organization
        query = Invitation.objects.filter(
            email__iexact=normalized_email,
            organization_id=organization_id,
            status__in=[Invitation.PENDING, Invitation.ACCEPTED, Invitation.CREATED]
        )
        
        if instance:
            query = query.exclude(id=instance.id)
            
        if query.exists():
            raise serializers.ValidationError(_('An invitation for this email already exists for this organization.'))
        
        return normalized_email
        
    except EmailNotValidError as e:
        raise serializers.ValidationError(str(e))
