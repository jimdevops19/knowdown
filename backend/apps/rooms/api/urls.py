from django.urls import path

from .views import RoomDetailView, RoomListView

app_name = "rooms"

urlpatterns = [
    path("", RoomListView.as_view(), name="room-list"),
    path("<slug:slug>/", RoomDetailView.as_view(), name="room-detail"),
]
