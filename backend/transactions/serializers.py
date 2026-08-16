from rest_framework import serializers
from .models import Transaction
from categories.serializers import CategorySerializer
from .ml_utils import detect_unusual_spending

from decimal import Decimal
from datetime import date, timedelta

class TransactionSerializer(serializers.ModelSerializer):
    category_name = serializers.ReadOnlyField(source='category.name')
    spending_insight = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = ['id', 'title', 'amount', 'category', 'category_name', 'type', 'date', 'notes', 'is_recurring', 'created_at', 'spending_insight']
        read_only_fields = ['created_at']

    def validate_amount(self, value):
        if value <= Decimal('0.00'):
            raise serializers.ValidationError("Transaction amount must be strictly greater than zero.")
        # Ensure max 2 decimal places
        if value.as_tuple().exponent < -2:
            raise serializers.ValidationError("Transaction amount cannot have more than 2 decimal places.")
        return value

    def validate_title(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Title cannot be blank.")
        return value.strip()

    def validate_date(self, value):
        # Prevent absurd future or past dates (> 5 years into future, > 50 years into past)
        today = date.today()
        if value > today + timedelta(days=365 * 5):
            raise serializers.ValidationError("Transaction date cannot be more than 5 years in the future.")
        if value < today - timedelta(days=365 * 50):
            raise serializers.ValidationError("Transaction date cannot be more than 50 years in the past.")
        return value

    def get_spending_insight(self, obj):
        if obj.type != 'EXPENSE':
            return None
        # Call ML util for unusual spending
        return detect_unusual_spending(obj.category, obj.amount, obj.user)
