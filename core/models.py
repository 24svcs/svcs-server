from django.db import models
from django.contrib.auth.models import AbstractUser
from timezone_field import TimeZoneField
import uuid


class User(AbstractUser):
    id = models.CharField(primary_key=True, default=uuid.uuid4, max_length=255)
    email = models.EmailField(unique=True)
    image_url = models.URLField(null=True, blank=True)
    timezone = TimeZoneField(default='UTC')


    def __str__(self):
        return  self.username
    

class Permission(models.Model):
    """
    Permission model defining access control for different entities in the system.
    Permissions are categorized by entity type and operation (view, create, edit, delete).
    Permissions can be assigned to members, or a groups.
    """
    
    # Permission Categories
    ORGANIZATION = "ORGANIZATION"
    STORE = "STORE"
    INVOICE = "INVOICE"
    MEMBER = "MEMBER"
    PAYMENT = "PAYMENT"
    ADDRESS = "ADDRESS"
    ROLE = "ROLE"
    GROUP = "GROUP"
    NOTIFICATION = "NOTIFICATION"
    DEPARTMENT = "DEPARTMENT"
    POSITION = "POSITION"
    EMPLOYEE = "EMPLOYEE"
    
    CATEGORY_CHOICES = [
        (ORGANIZATION, "Organization"),
        (STORE, "Store"),
        (INVOICE, "Invoice"),
        (MEMBER, "Member"),
        (PAYMENT, "Payment"),
        (ADDRESS, "Address"),
        (ROLE, "Role"),
        (GROUP, "Group"),
        (DEPARTMENT, "Department"),
        (POSITION, "Position"),
        (EMPLOYEE, "Employee"),
    ]
    
    # Company Permissions
    CREATE_ORGANIZATION = "CREATE_ORGANIZATION"
    VIEW_ORGANIZATION = "VIEW_ORGANIZATION"
    EDIT_ORGANIZATION = "EDIT_ORGANIZATION"
    DELETE_ORGANIZATION = "DELETE_ORGANIZATION"
    TRANSFER_OWNERSHIP = "TRANSFER_OWNERSHIP"
    
    # Company Address Permissions
    CREATE_ORGANIZATION_ADDRESSES = "CREATE_ORGANIZATION_ADDRESSES"
    VIEW_ORGANIZATION_ADDRESSES = "VIEW_ORGANIZATION_ADDRESSES"
    EDIT_ORGANIZATION_ADDRESSES = "EDIT_ORGANIZATION_ADDRESSES"
    DELETE_ORGANIZATION_ADDRESSES = "DELETE_ORGANIZATION_ADDRESSES"
    
    # Company Invoice Config Permissions
    CREATE_ORGANIZATION_INVOICE_CONFIG = "CREATE_ORGANIZATION_INVOICE_CONFIG"
    VIEW_ORGANIZATION_INVOICE_CONFIG = "VIEW_ORGANIZATION_INVOICE_CONFIG"
    EDIT_ORGANIZATION_INVOICE_CONFIG = "EDIT_ORGANIZATION_INVOICE_CONFIG"
    DELETE_ORGANIZATION_INVOICE_CONFIG = "DELETE_ORGANIZATION_INVOICE_CONFIG"
    
    
    # Comapny Invoice Item Permissions
    CREATE_ORGANIZATION_INVOICE_ITEM = "CREATE_ORGANIZATION_INVOICE_ITEM"
    VIEW_ORGANIZATION_INVOICE_ITEM = "VIEW_ORGANIZATION_INVOICE_ITEM"
    EDIT_ORGANIZATION_INVOICE_ITEM = "EDIT_ORGANIZATION_INVOICE_ITEM"
    DELETE_ORGANIZATION_INVOICE_ITEM = "DELETE_ORGANIZATION_INVOICE_ITEM"
    
    
    # Company Payment Method Permissions
    CREATE_ORGANIZATION_PAYMENT_METHOD = "CREATE_ORGANIZATION_PAYMENT_METHOD"
    VIEW_ORGANIZATION_PAYMENT_METHOD = "VIEW_ORGANIZATION_PAYMENT_METHOD"
    EDIT_ORGANIZATION_PAYMENT_METHOD = "EDIT_ORGANIZATION_PAYMENT_METHOD"
    DELETE_ORGANIZATION_PAYMENT_METHOD = "DELETE_ORGANIZATION_PAYMENT_METHOD"
    
    # Company Notification Preferences Permissions
    CREATE_ORGANIZATION_NOTIFICATION_PREFERENCES = "CREATE_ORGANIZATION_NOTIFICATION_PREFERENCES"
    VIEW_ORGANIZATION_NOTIFICATION_PREFERENCES = "VIEW_ORGANIZATION_NOTIFICATION_PREFERENCES"
    EDIT_ORGANIZATION_NOTIFICATION_PREFERENCES = "EDIT_ORGANIZATION_NOTIFICATION_PREFERENCES"
    DELETE_ORGANIZATION_NOTIFICATION_PREFERENCES = "DELETE_ORGANIZATION_NOTIFICATION_PREFERENCES"
    
    # Company Member Permissions
    VIEW_ORGANIZATION_MEMBER = "VIEW_ORGANIZATION_MEMBER"
    EDIT_ORGANIZATION_MEMBER = "EDIT_ORGANIZATION_MEMBER"
    DELETE_ORGANIZATION_MEMBER = "DELETE_ORGANIZATION_MEMBER"
    CREATE_MEMBER_INVITATION = 'CREATE_MEMBER_INVITATION'
    DELETE_MEMBER_INVITATION = 'DELETE_MEMBER_INVITATION'
    EDIT_MEMBER_INVITATION = 'EDIT_MEMBER_INVITATION'
    #todo
    
    
    # Company Role Permissions
    CREATE_ORGANIZATION_ROLE = "CREATE_ORGANIZATION_ROLE"
    VIEW_ORGANIZATION_ROLE = "VIEW_ORGANIZATION_ROLE"
    EDIT_ORGANIZATION_ROLE = "EDIT_ORGANIZATION_ROLE"
    DELETE_ORGANIZATION_ROLE = "DELETE_ORGANIZATION_ROLE"
    
    # Company Group Permissions
    CREATE_ORGANIZATION_GROUP = "CREATE_ORGANIZATION_GROUP"
    VIEW_ORGANIZATION_GROUP = "VIEW_ORGANIZATION_GROUP"
    EDIT_ORGANIZATION_GROUP = "EDIT_ORGANIZATION_GROUP"
    DELETE_ORGANIZATION_GROUP = "DELETE_ORGANIZATION_GROUP"
    
    # Company Department Permissions
    CREATE_ORGANIZATION_DEPARTMENT = "CREATE_ORGANIZATION_DEPARTMENT"
    VIEW_ORGANIZATION_DEPARTMENT = "VIEW_ORGANIZATION_DEPARTMENT"
    EDIT_ORGANIZATION_DEPARTMENT = "EDIT_ORGANIZATION_DEPARTMENT"
    DELETE_ORGANIZATION_DEPARTMENT = "DELETE_ORGANIZATION_DEPARTMENT"
    
    # Company Position Permissions
    CREATE_ORGANIZATION_POSITION = "CREATE_ORGANIZATION_POSITION"
    VIEW_ORGANIZATION_POSITION = "VIEW_ORGANIZATION_POSITION"
    EDIT_ORGANIZATION_POSITION = "EDIT_ORGANIZATION_POSITION"
    DELETE_ORGANIZATION_POSITION = "DELETE_ORGANIZATION_POSITION"
    
    # Company Employee Permissions
    CREATE_ORGANIZATION_EMPLOYEE = "CREATE_ORGANIZATION_EMPLOYEE"
    VIEW_ORGANIZATION_EMPLOYEE = "VIEW_ORGANIZATION_EMPLOYEE"
    EDIT_ORGANIZATION_EMPLOYEE = "EDIT_ORGANIZATION_EMPLOYEE"
    DELETE_ORGANIZATION_EMPLOYEE = "DELETE_ORGANIZATION_EMPLOYEE"
    
    
    
    # Map permissions to their categories
    PERMISSION_CATEGORY_MAP = {
        VIEW_ORGANIZATION: ORGANIZATION,
        EDIT_ORGANIZATION: ORGANIZATION,
        DELETE_ORGANIZATION: ORGANIZATION,
        TRANSFER_OWNERSHIP: ORGANIZATION,
        

        VIEW_ORGANIZATION_ADDRESSES: ADDRESS,
        EDIT_ORGANIZATION_ADDRESSES: ADDRESS,
        CREATE_ORGANIZATION_ADDRESSES: ADDRESS,
        DELETE_ORGANIZATION_ADDRESSES: ADDRESS,
        
        VIEW_ORGANIZATION_INVOICE_CONFIG: INVOICE,
        EDIT_ORGANIZATION_INVOICE_CONFIG: INVOICE,
        CREATE_ORGANIZATION_INVOICE_CONFIG: INVOICE,
        DELETE_ORGANIZATION_INVOICE_CONFIG: INVOICE,
        
        VIEW_ORGANIZATION_INVOICE_ITEM: INVOICE,
        EDIT_ORGANIZATION_INVOICE_ITEM: INVOICE,
        CREATE_ORGANIZATION_INVOICE_ITEM: INVOICE,
        DELETE_ORGANIZATION_INVOICE_ITEM: INVOICE,
        
        VIEW_ORGANIZATION_PAYMENT_METHOD: PAYMENT,
        EDIT_ORGANIZATION_PAYMENT_METHOD: PAYMENT,
        CREATE_ORGANIZATION_PAYMENT_METHOD: PAYMENT,
        DELETE_ORGANIZATION_PAYMENT_METHOD: PAYMENT,
        
        VIEW_ORGANIZATION_NOTIFICATION_PREFERENCES: NOTIFICATION,
        EDIT_ORGANIZATION_NOTIFICATION_PREFERENCES: NOTIFICATION,
        CREATE_ORGANIZATION_NOTIFICATION_PREFERENCES: NOTIFICATION,
        DELETE_ORGANIZATION_NOTIFICATION_PREFERENCES: NOTIFICATION,
        
        VIEW_ORGANIZATION_MEMBER: MEMBER,
        EDIT_ORGANIZATION_MEMBER: MEMBER,
        DELETE_ORGANIZATION_MEMBER: MEMBER,
        CREATE_MEMBER_INVITATION: MEMBER,
        DELETE_MEMBER_INVITATION: MEMBER,
        
        
        VIEW_ORGANIZATION_ROLE: ROLE,    
        EDIT_ORGANIZATION_ROLE: ROLE,
        CREATE_ORGANIZATION_ROLE: ROLE,
        DELETE_ORGANIZATION_ROLE: ROLE,
        
        VIEW_ORGANIZATION_GROUP: GROUP,
        EDIT_ORGANIZATION_GROUP: GROUP,
        CREATE_ORGANIZATION_GROUP: GROUP,
        DELETE_ORGANIZATION_GROUP: GROUP,
        
        VIEW_ORGANIZATION_DEPARTMENT: DEPARTMENT,
        EDIT_ORGANIZATION_DEPARTMENT: DEPARTMENT,
        CREATE_ORGANIZATION_DEPARTMENT: DEPARTMENT,
        DELETE_ORGANIZATION_DEPARTMENT: DEPARTMENT,
        
        VIEW_ORGANIZATION_POSITION: POSITION,
        EDIT_ORGANIZATION_POSITION: POSITION,
        CREATE_ORGANIZATION_POSITION: POSITION,
        DELETE_ORGANIZATION_POSITION: POSITION,
        
        VIEW_ORGANIZATION_EMPLOYEE: EMPLOYEE,   
        EDIT_ORGANIZATION_EMPLOYEE: EMPLOYEE,
        CREATE_ORGANIZATION_EMPLOYEE: EMPLOYEE,
        DELETE_ORGANIZATION_EMPLOYEE: EMPLOYEE,
        

    }
    
    # Define implied permissions (hierarchical structure)
    IMPLIED_PERMISSIONS = {
        EDIT_ORGANIZATION: [VIEW_ORGANIZATION],
        DELETE_ORGANIZATION: [VIEW_ORGANIZATION],

        EDIT_ORGANIZATION_ADDRESSES: [VIEW_ORGANIZATION_ADDRESSES],
        CREATE_ORGANIZATION_ADDRESSES: [VIEW_ORGANIZATION_ADDRESSES],
        DELETE_ORGANIZATION_ADDRESSES: [VIEW_ORGANIZATION_ADDRESSES],
        
        EDIT_ORGANIZATION_INVOICE_CONFIG: [VIEW_ORGANIZATION_INVOICE_CONFIG],
        CREATE_ORGANIZATION_INVOICE_CONFIG: [VIEW_ORGANIZATION_INVOICE_CONFIG],
        DELETE_ORGANIZATION_INVOICE_CONFIG: [VIEW_ORGANIZATION_INVOICE_CONFIG],
        
        EDIT_ORGANIZATION_INVOICE_ITEM: [VIEW_ORGANIZATION_INVOICE_ITEM],
        CREATE_ORGANIZATION_INVOICE_ITEM: [VIEW_ORGANIZATION_INVOICE_ITEM],
        DELETE_ORGANIZATION_INVOICE_ITEM: [VIEW_ORGANIZATION_INVOICE_ITEM],
        
        EDIT_ORGANIZATION_PAYMENT_METHOD: [VIEW_ORGANIZATION_PAYMENT_METHOD],
        CREATE_ORGANIZATION_PAYMENT_METHOD: [VIEW_ORGANIZATION_PAYMENT_METHOD],
        DELETE_ORGANIZATION_PAYMENT_METHOD: [VIEW_ORGANIZATION_PAYMENT_METHOD],
        
        EDIT_ORGANIZATION_NOTIFICATION_PREFERENCES: [VIEW_ORGANIZATION_NOTIFICATION_PREFERENCES],
        CREATE_ORGANIZATION_NOTIFICATION_PREFERENCES: [VIEW_ORGANIZATION_NOTIFICATION_PREFERENCES],
        DELETE_ORGANIZATION_NOTIFICATION_PREFERENCES: [VIEW_ORGANIZATION_NOTIFICATION_PREFERENCES],
        
        EDIT_ORGANIZATION_MEMBER: [VIEW_ORGANIZATION_MEMBER],
        DELETE_ORGANIZATION_MEMBER: [VIEW_ORGANIZATION_MEMBER],

        EDIT_ORGANIZATION_ROLE: [VIEW_ORGANIZATION_ROLE],
        CREATE_ORGANIZATION_ROLE: [VIEW_ORGANIZATION_ROLE],
        DELETE_ORGANIZATION_ROLE: [VIEW_ORGANIZATION_ROLE],
        
        EDIT_ORGANIZATION_GROUP: [VIEW_ORGANIZATION_GROUP],
        CREATE_ORGANIZATION_GROUP: [VIEW_ORGANIZATION_GROUP],
        DELETE_ORGANIZATION_GROUP: [VIEW_ORGANIZATION_GROUP],

        EDIT_ORGANIZATION_DEPARTMENT: [VIEW_ORGANIZATION_DEPARTMENT],
        CREATE_ORGANIZATION_DEPARTMENT: [VIEW_ORGANIZATION_DEPARTMENT],
        DELETE_ORGANIZATION_DEPARTMENT: [VIEW_ORGANIZATION_DEPARTMENT],
        
        EDIT_ORGANIZATION_POSITION: [VIEW_ORGANIZATION_POSITION],
        CREATE_ORGANIZATION_POSITION: [VIEW_ORGANIZATION_POSITION],
        DELETE_ORGANIZATION_POSITION: [VIEW_ORGANIZATION_POSITION],
        
        EDIT_ORGANIZATION_EMPLOYEE: [VIEW_ORGANIZATION_EMPLOYEE],   
        CREATE_ORGANIZATION_EMPLOYEE: [VIEW_ORGANIZATION_EMPLOYEE],
        DELETE_ORGANIZATION_EMPLOYEE: [VIEW_ORGANIZATION_EMPLOYEE],
        
    }
    
    PERMISSION_CHOICES = [
        (VIEW_ORGANIZATION, "View Organization Information"),
        (EDIT_ORGANIZATION, "Edit Organization Information"),
        (DELETE_ORGANIZATION, "Delete Organization Information"),
        (TRANSFER_OWNERSHIP, "Transfer Ownership"),
        
    
        (VIEW_ORGANIZATION_ADDRESSES, "View Organization Addresses"),
        (CREATE_ORGANIZATION_ADDRESSES, 'Create Organization Address'),
        (EDIT_ORGANIZATION_ADDRESSES, "Edit Organization Addresses"),
        (DELETE_ORGANIZATION_ADDRESSES, "Delete Organization Addresses"),
        
        (VIEW_ORGANIZATION_INVOICE_CONFIG, "View Organization Invoice Config"),
        (CREATE_ORGANIZATION_INVOICE_CONFIG, "Create Organization Invoice Config"),
        (EDIT_ORGANIZATION_INVOICE_CONFIG, "Edit Organization Invoice Config"),
        (DELETE_ORGANIZATION_INVOICE_CONFIG, "Delete Organization Invoice Config"),
        
        (VIEW_ORGANIZATION_INVOICE_ITEM, "View Organization Invoice Items"),
        (CREATE_ORGANIZATION_INVOICE_ITEM, "Create Organization Invoice Items"),
        (EDIT_ORGANIZATION_INVOICE_ITEM, "Edit Organization Invoice Items"),
        (DELETE_ORGANIZATION_INVOICE_ITEM, "Delete Organization Invoice Items"),
        
        (VIEW_ORGANIZATION_PAYMENT_METHOD, "View Organization Payment Methods"),
        (CREATE_ORGANIZATION_PAYMENT_METHOD, "Create Organization Payment Methods"),
        (EDIT_ORGANIZATION_PAYMENT_METHOD, "Edit Organization Payment Methods"),
        (DELETE_ORGANIZATION_PAYMENT_METHOD, "Delete Organization Payment Methods"),
        
        (VIEW_ORGANIZATION_NOTIFICATION_PREFERENCES, "View Organization Notification Preferences"),
        (CREATE_ORGANIZATION_NOTIFICATION_PREFERENCES, "Create Organization Notification Preferences"),
        (EDIT_ORGANIZATION_NOTIFICATION_PREFERENCES, "Edit Organization Notification Preferences"),
        (DELETE_ORGANIZATION_NOTIFICATION_PREFERENCES, "Delete Organization Notification Preferences"),
        
        (VIEW_ORGANIZATION_MEMBER, "View Organization Members"),
        (EDIT_ORGANIZATION_MEMBER, "Edit Organization Members"),
        (DELETE_ORGANIZATION_MEMBER, "Delete Organization Members"),
        (CREATE_MEMBER_INVITATION, 'Create Member Invitation'),
        (DELETE_MEMBER_INVITATION, 'Delete Member Invitation'),
        (EDIT_MEMBER_INVITATION, 'EDIT Member Invitation'),

        
        (VIEW_ORGANIZATION_ROLE, "View Organization Roles"),
        (CREATE_ORGANIZATION_ROLE, "Create Organization Roles"),
        (EDIT_ORGANIZATION_ROLE, "Edit Organization Roles"),
        (DELETE_ORGANIZATION_ROLE, "Delete Organization Roles"),
        
        (VIEW_ORGANIZATION_GROUP, "View Organization Groups"),
        (CREATE_ORGANIZATION_GROUP, "Create Organization Groups"),
        (EDIT_ORGANIZATION_GROUP, "Edit Organization Groups"),
        (DELETE_ORGANIZATION_GROUP, "Delete Organization Groups"),

        (VIEW_ORGANIZATION_DEPARTMENT, "View Organization Departments"),
        (CREATE_ORGANIZATION_DEPARTMENT, "Create Organization Departments"),
        (EDIT_ORGANIZATION_DEPARTMENT, "Edit Organization Departments"),
        (DELETE_ORGANIZATION_DEPARTMENT, "Delete Organization Departments"),
        
        (VIEW_ORGANIZATION_POSITION, "View Organization Positions"),
        (CREATE_ORGANIZATION_POSITION, "Create Organization Positions"),
        (EDIT_ORGANIZATION_POSITION, "Edit Organization Positions"),
        (DELETE_ORGANIZATION_POSITION, "Delete Organization Positions"),
        
        (VIEW_ORGANIZATION_EMPLOYEE, "View Organization Employees"),
        (CREATE_ORGANIZATION_EMPLOYEE, "Create Organization Employees"),
        (EDIT_ORGANIZATION_EMPLOYEE, "Edit Organization Employees"),
        (DELETE_ORGANIZATION_EMPLOYEE, "Delete Organization Employees"),
        
    ]
    
    name = models.CharField(max_length=100, choices=PERMISSION_CHOICES, unique=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, blank=True, null=True, editable=False)
    description = models.TextField(null=True, blank=True)


    class Meta:
        verbose_name_plural = "Permissions"
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['category']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['name'], name='unique_permission_name')
        ]
        
    def __str__(self):
        return self.get_name_display()
    
    def save(self, *args, **kwargs):
        """
        Override save method to automatically set the category based on permission name
        """
        if self.name in self.PERMISSION_CATEGORY_MAP:
            self.category = self.PERMISSION_CATEGORY_MAP[self.name]
        super().save(*args, **kwargs)
    
    @classmethod
    def get_implied_permissions(cls, permission_name):
        """
        Returns a list of permission names that are implied by the given permission.
        For example, if a user has EDIT_COMPANY permission, they implicitly have VIEW_COMPANY.
        
        Args:
            permission_name (str): The name of the permission to check
            
        Returns:
            list: List of implied permission names
        """
        return cls.IMPLIED_PERMISSIONS.get(permission_name, [])


class Language(models.Model):
    ENGLISH = 'en'
    SPANISH = 'es'
    FRENCH = 'fr'
    KREYOL = 'ht'
    
    LANGUAGE_CHOICES = [
        (ENGLISH, 'English'),
        (SPANISH, 'Spanish'),
        (FRENCH, 'French'),
        (KREYOL, 'Kreyol'),
    ]
    
    LANGUAGE_MAP = dict(LANGUAGE_CHOICES)

    code = models.CharField(max_length=2, choices=LANGUAGE_CHOICES, unique=True)
    name = models.CharField(max_length=50, editable=False)

    def save(self, *args, **kwargs):
        """Automatically set the human-readable name before saving."""
        self.name = self.LANGUAGE_MAP.get(self.code, "Unknown")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Languages"
        indexes = [
            models.Index(fields=['name']),
        ]
    

    
    
