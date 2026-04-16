from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse


def health_check(request):
    """Lightweight endpoint to wake up Render from cold start."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health_check, name='health_check'),
    path('api/auth/', include('accounts.urls')),
    path('api/categories/', include('categories.urls')),
    path('api/transactions/', include('transactions.urls')),
]
