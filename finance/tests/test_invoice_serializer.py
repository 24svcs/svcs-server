from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from ..models import Invoice, InvoiceItem, Client
from ..serializers import CreateInvoiceSerializer
from django.contrib.auth import get_user_model
from organization.models import Organization

User = get_user_model()

class TestCreateInvoiceSerializer(TestCase):
    def setUp(self):
        # Create test user and organization
        self.user = User.objects.create(
            email="test@example.com",
            password="testpass123"
        )
        
        self.organization = Organization.objects.create(
            user=self.user,
            name="Test Organization",
            name_space="test-org",
            organization_type="ENTERPRISE",
            email="org@test.com",
            phone="+1234567890",
            industry="Technology"
        )
        
        self.client = Client.objects.create(
            organization=self.organization,
            name="Test Client",
            email="client@test.com",
            is_active=True
        )

        self.valid_data = {
            'client_id': self.client.id,
            'issue_date': timezone.now().date(),
            'due_date': (timezone.now() + timezone.timedelta(days=30)).date(),
            'tax_rate': Decimal('10.00'),
            'notes': "Test invoice",
            'late_fee_percentage': Decimal('5.00'),
            'allow_partial_payments': False,
            'minimum_payment_amount': Decimal('0.00'),
            'items': [
                {
                    'product': "Test Product",
                    'description': "Test Description",
                    'quantity': Decimal('2'),
                    'unit_price': Decimal('100.00')
                }
            ]
        }

        self.serializer_context = {
            'organization_id': self.organization.id
        }

    def test_valid_data_creation(self):
        """Test creating an invoice with valid data"""
        serializer = CreateInvoiceSerializer(data=self.valid_data, context=self.serializer_context)
        if not serializer.is_valid():
            print("Validation errors:", serializer.errors)
        self.assertTrue(serializer.is_valid())
        invoice = serializer.save()
        
        self.assertEqual(invoice.client_id, self.client.id)
        self.assertEqual(invoice.tax_rate, Decimal('10.00'))
        self.assertEqual(invoice.items.count(), 1)
        self.assertTrue(invoice.invoice_number.startswith('INV-'))

    def test_invalid_client_id(self):
        """Test validation with non-existent client ID"""
        data = self.valid_data.copy()
        data['client_id'] = 99999
        
        serializer = CreateInvoiceSerializer(data=data, context=self.serializer_context)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_inactive_client(self):
        """Test validation with inactive client"""
        self.client.is_active = False
        self.client.save()
        
        serializer = CreateInvoiceSerializer(data=self.valid_data, context=self.serializer_context)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_future_issue_date(self):
        """Test validation with future issue date"""
        data = self.valid_data.copy()
        data['issue_date'] = (timezone.now() + timezone.timedelta(days=1)).date()
        
        serializer = CreateInvoiceSerializer(data=data, context=self.serializer_context)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_due_date_before_issue_date(self):
        """Test validation with due date before issue date"""
        data = self.valid_data.copy()
        data['due_date'] = (timezone.now() - timezone.timedelta(days=1)).date()
        
        serializer = CreateInvoiceSerializer(data=data, context=self.serializer_context)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_invalid_tax_rate(self):
        """Test validation with invalid tax rates"""
        test_cases = [-1, 101, 'invalid']
        
        for tax_rate in test_cases:
            data = self.valid_data.copy()
            data['tax_rate'] = tax_rate
            
            serializer = CreateInvoiceSerializer(data=data, context=self.serializer_context)
            with self.assertRaises(ValidationError):
                serializer.is_valid(raise_exception=True)

    def test_no_items(self):
        """Test validation with no invoice items"""
        data = self.valid_data.copy()
        data['items'] = []
        
        serializer = CreateInvoiceSerializer(data=data, context=self.serializer_context)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_invalid_item_quantity(self):
        """Test validation with invalid item quantities"""
        test_cases = [0, -1, 'invalid']
        
        for quantity in test_cases:
            data = self.valid_data.copy()
            data['items'] = [{
                'product': "Test Product",
                'description': "Test Description",
                'quantity': quantity,
                'unit_price': Decimal('100.00')
            }]
            
            serializer = CreateInvoiceSerializer(data=data, context=self.serializer_context)
            with self.assertRaises(ValidationError):
                serializer.is_valid(raise_exception=True)

    def test_invalid_unit_price(self):
        """Test validation with invalid unit prices"""
        test_cases = [-1, 'invalid']
        
        for price in test_cases:
            data = self.valid_data.copy()
            data['items'] = [{
                'product': "Test Product",
                'description': "Test Description",
                'quantity': Decimal('1'),
                'unit_price': price
            }]
            
            serializer = CreateInvoiceSerializer(data=data, context=self.serializer_context)
            with self.assertRaises(ValidationError):
                serializer.is_valid(raise_exception=True)

    def test_partial_payment_settings(self):
        """Test validation of partial payment settings"""
        # Test invalid: allow_partial=True with minimum_payment=0
        data = self.valid_data.copy()
        data['allow_partial_payments'] = True
        data['minimum_payment_amount'] = Decimal('0')
        
        serializer = CreateInvoiceSerializer(data=data, context=self.serializer_context)
        self.assertFalse(serializer.is_valid())
        self.assertIn('minimum_payment_amount', serializer.errors)
        self.assertEqual(
            str(serializer.errors['minimum_payment_amount'][0]),
            "Minimum payment amount must be greater than 0 when partial payments are allowed"
        )

        # Test invalid: allow_partial=False with minimum_payment>0
        data['allow_partial_payments'] = False
        data['minimum_payment_amount'] = Decimal('50.00')
        
        serializer = CreateInvoiceSerializer(data=data, context=self.serializer_context)
        self.assertFalse(serializer.is_valid())
        self.assertIn('minimum_payment_amount', serializer.errors)
        self.assertEqual(
            str(serializer.errors['minimum_payment_amount'][0]),
            "Minimum payment amount should be 0 when partial payments are not allowed"
        )

        # Test valid: allow_partial=True with minimum_payment>0
        data['allow_partial_payments'] = True
        data['minimum_payment_amount'] = Decimal('50.00')
        serializer = CreateInvoiceSerializer(data=data, context=self.serializer_context)
        self.assertTrue(serializer.is_valid())

        # Test valid: allow_partial=False with minimum_payment=0
        data['allow_partial_payments'] = False
        data['minimum_payment_amount'] = Decimal('0')
        serializer = CreateInvoiceSerializer(data=data, context=self.serializer_context)
        self.assertTrue(serializer.is_valid())

    def test_late_fee_percentage(self):
        """Test validation of late fee percentage"""
        test_cases = [-1, 101, 'invalid']
        
        for late_fee in test_cases:
            data = self.valid_data.copy()
            data['late_fee_percentage'] = late_fee
            
            serializer = CreateInvoiceSerializer(data=data, context=self.serializer_context)
            with self.assertRaises(ValidationError):
                serializer.is_valid(raise_exception=True)

    def test_unique_invoice_number_generation(self):
        """Test that generated invoice numbers are unique"""
        # Create multiple invoices and verify unique invoice numbers
        created_numbers = set()
        for _ in range(5):
            serializer = CreateInvoiceSerializer(data=self.valid_data, context=self.serializer_context)
            self.assertTrue(serializer.is_valid())
            invoice = serializer.save()
            
            self.assertNotIn(invoice.invoice_number, created_numbers)
            created_numbers.add(invoice.invoice_number)
            self.assertTrue(invoice.invoice_number.startswith('INV-'))
            self.assertEqual(len(invoice.invoice_number), 10)  # 'INV-' + 6 chars

    def test_draft_status_on_creation(self):
        """Test that new invoices are created with DRAFT status"""
        serializer = CreateInvoiceSerializer(data=self.valid_data, context=self.serializer_context)
        self.assertTrue(serializer.is_valid())
        invoice = serializer.save()
        
        self.assertEqual(invoice.status, 'DRAFT')

    def test_minimum_payment_validation(self):
        """Test validation of minimum payment amount relative to invoice total"""
        # Calculate total invoice amount (2 items * $100 each + 10% tax)
        total_amount = Decimal('220.00')  # (2 * 100) + 10% tax
        
        # Test: minimum payment greater than total amount
        data = self.valid_data.copy()
        data['minimum_payment_amount'] = total_amount + Decimal('1.00')
        
        serializer = CreateInvoiceSerializer(data=data, context=self.serializer_context)
        self.assertFalse(serializer.is_valid())
        self.assertIn('minimum_payment_amount', serializer.errors)
        self.assertEqual(
            str(serializer.errors['minimum_payment_amount'][0]),
            "Minimum payment amount cannot be greater than the total invoice amount"
        )

        # Test: partial payments with minimum equal to total
        data['allow_partial_payments'] = True
        data['minimum_payment_amount'] = total_amount
        
        serializer = CreateInvoiceSerializer(data=data, context=self.serializer_context)
        self.assertFalse(serializer.is_valid())
        self.assertIn('minimum_payment_amount', serializer.errors)
        self.assertEqual(
            str(serializer.errors['minimum_payment_amount'][0]),
            "When partial payments are allowed, minimum payment amount must be less than the total invoice amount"
        )

        # Test valid: partial payments with minimum less than total
        data['minimum_payment_amount'] = total_amount / Decimal('2')
        serializer = CreateInvoiceSerializer(data=data, context=self.serializer_context)
        self.assertTrue(serializer.is_valid())

        # Test valid: no partial payments with zero minimum
        data['allow_partial_payments'] = False
        data['minimum_payment_amount'] = Decimal('0')
        serializer = CreateInvoiceSerializer(data=data, context=self.serializer_context)
        self.assertTrue(serializer.is_valid()) 