from django.urls import path
from . import callbacks, views

app_name = "payments"

urlpatterns = [
    path("channels/", views.channel_list, name="channel_list"),
    path("channels/new/step1/", views.channel_form_step1, name="channel_step1"),
    path("channels/new/step2/", views.channel_form_step2, name="channel_step2"),
    path("callbacks/daraja/", callbacks.daraja_callback, name="daraja_callback"),
]
