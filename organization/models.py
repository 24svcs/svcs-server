from django.db import models
from timezone_field import TimeZoneField
from phonenumber_field.modelfields import PhoneNumberField
from uuid import uuid4
from core.models import User, Permission, Language
from django.core.exceptions import ValidationError
from django.utils.timezone import now, timedelta


class OrganizationManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)
    
class AllOrganizationManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset()
    


# <========== Organization Model ==========> #
class Organization(models.Model):
    
    ENTERPRISE = 'ENTERPRISE'
    SOLO = 'SOLO'
    TEAM = 'TEAM'
    
    ORGANIZATION_TYPE_CHOICES = [
        (ENTERPRISE, 'Enterprise'),
        (SOLO, 'Solo'),
        (TEAM, 'Team'),
    ]
    
     # Member limits by organization type
    MEMBER_LIMITS = {
        SOLO: 1,
        TEAM: 20,
        ENTERPRISE: 50,
    }

    
    
    id = models.UUIDField(default=uuid4, primary_key=True, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='organization')
    name = models.CharField(max_length=64, unique=True)
    name_space = models.CharField(max_length=70, unique=True)
    organization_type = models.CharField(max_length=10, choices=ORGANIZATION_TYPE_CHOICES, default=SOLO)
    email = models.EmailField(unique=True)
    phone = PhoneNumberField(unique=True)
    description = models.TextField(max_length=1000)
    tax_id = models.CharField(max_length=255, blank=True, null=True)
    industry = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    logo_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    
    objects = OrganizationManager()
    all_objects = AllOrganizationManager()
    
    class Meta:
        verbose_name_plural = "Organizations"
        
        indexes = [
            
            models.Index(fields=['name']),
            models.Index(fields=['email']),
            models.Index(fields=['phone']),
            models.Index(fields=['name_space']),
        ]
        
        constraints = [
            models.UniqueConstraint(fields=['name', 'email', 'phone', 'name_space'], name='unique_info')
        ]
        
    
    def get_member_limit(self):
        """Return the maximum number of members allowed for this organization type."""
        return self.MEMBER_LIMITS.get(self.organization_type, 1)
    
    def can_add_member(self):
        """Check if the organization can add more members."""
        current_member_count = self.members.only('id').count()
        return current_member_count < self.get_member_limit()
    
    def get_available_members(self):
        """Return the number of available members for the organization."""
        return self.get_member_limit() - self.members.only('id').count()
        
    def __str__(self):
        return self.name
    
    def soft_delete(self):
        self.is_active = False
        self.save()
        
    def is_member(self, user):
        """Check if a user is a member of the organization."""
        return self.members.filter(user=user, status=Member.ACTIVE).values_list('id', flat=True).exists()
        
    def is_admin(self, user):
        """Check if a user is an admin of the organization."""
        return self.members.filter(user=user, status=Member.ACTIVE, is_admin=True).values_list('id', flat=True).exists()
        


class Member(models.Model):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    
 
    MEMBER_STATUS_CHOICES = [
        (ACTIVE, "Active"),
        (INACTIVE, "Inactive"),
    ]
    
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    status = models.CharField(max_length=20, choices=MEMBER_STATUS_CHOICES, default=INACTIVE)
    permissions = models.ManyToManyField(Permission, related_name='members', blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    is_owner = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)   
    last_active_at = models.DateTimeField(null=True, blank=True) 
    
    class Meta:
        verbose_name_plural = "Members"
        constraints = [
            models.UniqueConstraint(fields=['organization', 'user'], name='unique_user_per_organization')
        ]
        indexes = [
            models.Index(fields=['organization']),
            models.Index(fields=['user']),
            models.Index(fields=['status']),
        ]
    
    def clean(self):
        if self.organization.members.count() >= self.organization.get_member_limit():
            raise ValidationError("This organization has reached its member limit.")

    def __str__(self):
        return f"{self.user} (Organization: {self.organization.name})"
    
    
def default_expiration():
    return now() + timedelta(days=7)

class MemberInvitation(models.Model):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    
    INVITATION_STATUS_CHOICES = [
        (PENDING, "Pending"),
        (ACCEPTED, "Accepted"),
        (REJECTED, "Rejected"),
    ]
    
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField()
    name = models.CharField(max_length=255)
    message = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=INVITATION_STATUS_CHOICES, default=PENDING)
    invited_at = models.DateTimeField(auto_now_add=True)
    invited_by = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='+', null=True)
    is_updated = models.BooleanField(editable=False, default=False)
    expires_at = models.DateTimeField(default=default_expiration)

    def is_expired(self):
        return self.status == self.PENDING and self.expires_at < now()
    
    class Meta:
        verbose_name_plural = "Invitations"
        
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'email'],
                condition=models.Q(status="PENDING"),
                name='unique_pending_invitation_per_email'
            ),
            models.UniqueConstraint(
                fields=['organization', 'email'],
                condition=models.Q(status="ACCEPTED"),
                name='unique_accepted_invitation_per_email'
            )
        ]
        
        indexes = [
            models.Index(fields=['organization']),
            models.Index(fields=['email']),
            models.Index(fields=['status']),
        ]
        
    def __str__(self):
        return f"{self.email} (Organization: {self.organization.name})"



# <========== Preferences Model ==========> #
class Preference(models.Model):
    
    DARK = 'dark'
    LIGHT = 'light'
    SYSTEM = 'system'
    
    
    MODE_CHOICES = [
        (DARK, 'Dark'),
        (LIGHT, 'Light'),
        (SYSTEM, 'System')
    ]

    
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name='preferences')
    theme  = models.CharField(max_length=6, choices=MODE_CHOICES, default=SYSTEM)
    language = models.ForeignKey(Language, on_delete=models.PROTECT, default=1)  # Assuming English has ID=1
    timezone = TimeZoneField(default='UTC')
    
    def __str__(self):
        return f"Preferences for {self.organization.name}"
    
    class Meta:
        verbose_name_plural = "Preferences"
