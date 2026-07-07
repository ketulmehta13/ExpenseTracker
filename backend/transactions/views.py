from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
import csv
from django.http import HttpResponse
from decimal import Decimal

from .models import Transaction
from .serializers import TransactionSerializer
from categories.models import Category

class TransactionViewSet(viewsets.ModelViewSet):
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Filter by user
        queryset = Transaction.objects.filter(user=self.request.user)
        
        # Filter by type
        transaction_type = self.request.query_params.get('type')
        if transaction_type:
            queryset = queryset.filter(type=transaction_type.upper())
            
        # Filter by category
        category_id = self.request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
            
        return queryset

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        now = timezone.now()
        current_month = now.month
        current_year = now.year

        # Previous month calculation
        first_day_current = now.replace(day=1)
        last_day_prev = first_day_current - timedelta(days=1)
        prev_month = last_day_prev.month
        prev_year = last_day_prev.year

        # Helper function
        def get_stats(month, year):
            txs = self.get_queryset().filter(date__month=month, date__year=year)
            income = txs.filter(type='INCOME').aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
            expense = txs.filter(type='EXPENSE').aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
            return income, expense, txs
        
        curr_income, curr_expense, curr_txs = get_stats(current_month, current_year)
        prev_income, prev_expense, _ = get_stats(prev_month, prev_year)

        budget = request.user.monthly_budget or Decimal('0.00')
        remaining = budget - curr_expense if budget > 0 else Decimal('0.00')

        # Percent change in expense
        if prev_expense > 0:
            expense_change_pct = ((curr_expense - prev_expense) / prev_expense) * 100
        else:
            expense_change_pct = 100 if curr_expense > 0 else 0

        insight = ""
        if expense_change_pct > 0:
            insight = f"You spent {expense_change_pct:.1f}% more this month compared to last month."
        elif expense_change_pct < 0:
            insight = f"Great job! You spent {abs(expense_change_pct):.1f}% less this month."
        
        # Category breakdown for current month
        cat_expenses = curr_txs.filter(type='EXPENSE').values('category__name').annotate(total=Sum('amount'))
        
        return Response({
            'current_month': {
                'income': curr_income,
                'expense': curr_expense,
                'balance': curr_income - curr_expense,
            },
            'previous_month': {
                'income': prev_income,
                'expense': prev_expense,
            },
            'budget': {
                'limit': budget,
                'remaining': remaining,
                'exceeded': curr_expense > budget if budget > 0 else False
            },
            'insights': insight,
            'category_breakdown': list(cat_expenses)
        })

    @action(detail=False, methods=['get'])
    def export(self, request):
        queryset = self.get_queryset()
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="transactions.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Date', 'Title', 'Category', 'Type', 'Amount', 'Notes', 'Is Recurring'])
        
        for tx in queryset:
            writer.writerow([
                tx.date, 
                tx.title, 
                tx.category.name if tx.category else 'Uncategorized',
                tx.type,
                tx.amount,
                tx.notes or '',
                tx.is_recurring
            ])
            
        return response

    @action(detail=False, methods=['get'])
    def suggest_category(self, request):
        title = request.query_params.get('title', '').lower()
        if not title:
            return Response({'suggested_category': None})
            
        # Basic keyword mapper
        keywords = {
            'Food': ['uber eats', 'swiggy', 'mcdonalds', 'kfc', 'restaurant', 'lunch', 'dinner', 'groceries', 'zomato', 'pizza', 'breakfast'],
            'Travel': ['uber', 'lyft', 'flight', 'train', 'bus', 'fuel', 'gas', 'ticket', 'indigo', 'taxi', 'petrol'],
            'Entertainment': ['netflix', 'spotify', 'movie', 'cinema', 'prime', 'game'],
            'Utilities': ['electricity', 'water', 'internet', 'wifi', 'phone', 'bill', 'recharge'],
            'Rent': ['rent', 'lease', 'deposit', 'maintenance'],
            'Salary': ['salary', 'wages', 'paycheck', 'bonus'],
            'Shopping': ['amazon', 'flipkart', 'myntra', 'clothes', 'shoes', 'electronics']
        }
        
        suggested = None
        for category_name, words in keywords.items():
            if any(word in title for word in words):
                suggested = category_name
                break
                
        if suggested:
            # try to find category by name or create it for user if it doesn't exist
            cat = Category.objects.filter(name__iexact=suggested, user=request.user).first()
            if not cat:
                cat = Category.objects.filter(name__iexact=suggested, user__isnull=True).first()
            if cat:
                return Response({'suggested_category': cat.id})
                
        return Response({'suggested_category': None})

    @action(detail=False, methods=['get'], url_path='insights/category-stats')
    def category_stats(self, request):
        import numpy as np
        from collections import defaultdict
        
        expenses = Transaction.objects.filter(user=request.user, type='EXPENSE').select_related('category')
        
        category_amounts = defaultdict(list)
        for tx in expenses:
            cat_name = tx.category.name if tx.category else 'Uncategorized'
            category_amounts[cat_name].append(float(tx.amount))
            
        stats = []
        for cat_name, amounts in category_amounts.items():
            count = len(amounts)
            if count > 0:
                mean = np.mean(amounts)
                std = np.std(amounts)
                stats.append({
                    "category": cat_name,
                    "mean": round(float(mean), 2),
                    "std": round(float(std), 2),
                    "count": count
                })
                
        return Response(stats)
