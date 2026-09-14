from django.urls import path
from . import views
from . import auth_views

urlpatterns = [
    path('upload/', views.upload),
    path('run_model/', views.run_model),
    path('pop/<str:params_id>', views.run_model),
    path('auth/login', auth_views.login),
    path('auth/callback', auth_views.auth_callback),
    path('auth/logout', auth_views.logout),
    path('auth/status', auth_views.status),
]
