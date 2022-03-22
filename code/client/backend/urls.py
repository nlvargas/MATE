from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.upload),
    path('run_model/', views.run_model),
    path('pop/<str:params_id>', views.run_model),
]