from django.urls import path

from parking import views

app_name = "parking"

urlpatterns = [
    path("pay/", views.pay_view, name="pay"),
    path("session/<int:session_id>/", views.session_status_view, name="session_status"),
]
