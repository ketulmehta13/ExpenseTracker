from rest_framework import serializers
from .models import Transaction
from categories.serializers import CategorySerializer

class TransactionSerializer(serializers.ModelSerializer):
    category_name = serializers.ReadOnlyField(source='category.name')

    class Meta:
        model = Transaction
        fields = ['id', 'title', 'amount', 'category', 'category_name', 'type', 'date', 'notes', 'is_recurring', 'created_at']
        read_only_fields = ['created_at']
