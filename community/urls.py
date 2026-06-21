from django.urls import path

from .views import (
    CommentCreateView,
    CommentDetailView,
    LikeToggleView,
    PostDetailView,
    PostListCreateView,
    PublicProfileView,
    SaveSharedMealView,
    SaveSharedRoutineView,
)


urlpatterns = [
    path('users/<int:user_id>/public-profile/', PublicProfileView.as_view(), name='public-profile'),
    path('posts/', PostListCreateView.as_view(), name='post-list-create'),
    path('posts/<int:post_id>/', PostDetailView.as_view(), name='post-detail'),
    path('posts/<int:post_id>/comments/', CommentCreateView.as_view(), name='comment-create'),
    path('comments/<int:comment_id>/', CommentDetailView.as_view(), name='comment-detail'),
    path('posts/<int:post_id>/like/', LikeToggleView.as_view(), name='post-like-toggle'),
    path(
        'posts/<int:post_id>/save-shared-meal/',
        SaveSharedMealView.as_view(),
        name='post-save-shared-meal',
    ),
    path(
        'posts/<int:post_id>/save-shared-routine/',
        SaveSharedRoutineView.as_view(),
        name='post-save-shared-routine',
    ),
]
