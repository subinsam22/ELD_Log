from django.urls import path

from api import views


urlpatterns = [
    path('plan-trip/', views.plan_trip, name='search_results'),
]
