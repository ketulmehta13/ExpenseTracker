from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    """
    Custom user model for the Expense Tracker.
    """
    monthly_budget = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Monthly budget limit for the user")
    phone = models.CharField(max_length=20, blank=True, default='', help_text="Phone number")
    profile_photo = models.TextField(blank=True, default='', help_text="Base64 encoded profile photo")
