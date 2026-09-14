from django.urls import path, include
from django.conf import settings


if settings.DEBUG:
    urlpatterns = [
        path('dev/', include('backend.urls')),
        path('', include('frontend.urls'))
    ]
else:
    urlpatterns = [
        path('', include('backend.urls')),
        path('', include('frontend.urls'))
    ]
