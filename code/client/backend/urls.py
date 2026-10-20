from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.upload),
    path('run_model/', views.run_model),
    path('run_sensitivity_analysis/', views.run_sensitivity_analysis),
    path('pop/<str:params_id>', views.remove_params_from_queue),
]
