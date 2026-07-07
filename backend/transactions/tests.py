from django.test import TestCase
from django.contrib.auth import get_user_model
from categories.models import Category
from .models import Transaction
from .ml_utils import detect_unusual_spending
import decimal

User = get_user_model()

class SpendingInsightsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='password123')
        self.category = Category.objects.create(name='Groceries', user=self.user)
        
    def test_detect_unusual_spending(self):
        # Create 5 normal transactions around $50
        amounts = [48, 52, 50, 49, 51]
        for amt in amounts:
            Transaction.objects.create(
                user=self.user,
                title='Grocery Run',
                amount=decimal.Decimal(amt),
                category=self.category,
                type=Transaction.TransactionType.EXPENSE,
                date='2026-07-01'
            )
            
        # The mean of 48, 52, 50, 49, 51 is 50.
        # The std is sqrt((4+4+0+1+1)/5) = sqrt(10/5) = sqrt(2) = ~1.414
        
        # Test a normal amount
        normal_amount = decimal.Decimal('51.00')
        result_normal = detect_unusual_spending(self.category, normal_amount, self.user)
        self.assertFalse(result_normal['is_unusual'])
        self.assertEqual(result_normal['category_mean'], 50.0)
        
        # Test an unusually high amount (e.g. 100)
        # z-score = (100 - 50) / 1.414 = ~35.3 > 2 (unusual)
        high_amount = decimal.Decimal('100.00')
        result_high = detect_unusual_spending(self.category, high_amount, self.user)
        self.assertTrue(result_high['is_unusual'])
        self.assertTrue(result_high['z_score'] > 2)
        
    def test_not_enough_data(self):
        # Create only 3 transactions
        amounts = [50, 50, 50]
        for amt in amounts:
            Transaction.objects.create(
                user=self.user,
                title='Grocery Run',
                amount=decimal.Decimal(amt),
                category=self.category,
                type=Transaction.TransactionType.EXPENSE,
                date='2026-07-01'
            )
            
        result = detect_unusual_spending(self.category, decimal.Decimal('100.00'), self.user)
        self.assertFalse(result['is_unusual'])
        self.assertEqual(result['category_mean'], 0.0)

    def test_zero_std_deviation(self):
        # Create 5 identical transactions
        for _ in range(5):
            Transaction.objects.create(
                user=self.user,
                title='Subscription',
                amount=decimal.Decimal('10.00'),
                category=self.category,
                type=Transaction.TransactionType.EXPENSE,
                date='2026-07-01'
            )
            
        # Higher than mean with 0 std
        result = detect_unusual_spending(self.category, decimal.Decimal('15.00'), self.user)
        self.assertTrue(result['is_unusual'])
        self.assertEqual(result['z_score'], float('inf'))
