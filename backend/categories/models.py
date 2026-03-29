from django.db import models
from django.conf import settings

class Category(models.Model):
    name = models.CharField(max_length=50)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        help_text="If null, this is a default category accessible to all users."
    )

    class Meta:
        verbose_name_plural = "Categories"
        unique_together = ('name', 'user')

    def __str__(self):
        return self.name
