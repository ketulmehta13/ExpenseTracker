from rest_framework import serializers
from .models import Transaction
from categories.serializers import CategorySerializer
from .ml_utils import detect_unusual_spending

class TransactionSerializer(serializers.ModelSerializer):
    category_name = serializers.ReadOnlyField(source='category.name')
    spending_insight = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = ['id', 'title', 'amount', 'category', 'category_name', 'type', 'date', 'notes', 'is_recurring', 'created_at', 'spending_insight']
        read_only_fields = ['created_at']

    def get_spending_insight(self, obj):
        if obj.type != 'EXPENSE':
            return None
        # Call ML util for unusual spending
        return detect_unusual_spending(obj.category, obj.amount, obj.user)
