from django.urls import path

from .views import BodyRecordDetailView, BodyRecordListCreateView, ProgressView


urlpatterns = [
    path('body-records/', BodyRecordListCreateView.as_view(), name='body-record-list-create'),
    path(
        'body-records/<int:body_record_id>/',
        BodyRecordDetailView.as_view(),
        name='body-record-detail',
    ),
    path('progress/', ProgressView.as_view(), name='progress'),
]
