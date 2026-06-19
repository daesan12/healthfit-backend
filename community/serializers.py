from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Comment, Post


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ['id', 'username']


class CommentSerializer(serializers.ModelSerializer):
    author = UserSummarySerializer(source='user', read_only=True)
    post_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Comment
        fields = [
            'id',
            'post_id',
            'author',
            'content',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class PostSerializer(serializers.ModelSerializer):
    author = UserSummarySerializer(source='user', read_only=True)
    comment_count = serializers.SerializerMethodField()
    like_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            'id',
            'author',
            'title',
            'content',
            'category',
            'comment_count',
            'like_count',
            'is_liked',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_comment_count(self, obj):
        return obj.comments.count()

    def get_like_count(self, obj):
        return obj.likes.count()

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request is None or not request.user.is_authenticated:
            return False
        return any(like.user_id == request.user.id for like in obj.likes.all())


class PostDetailSerializer(PostSerializer):
    comments = CommentSerializer(many=True, read_only=True)

    class Meta(PostSerializer.Meta):
        fields = [*PostSerializer.Meta.fields, 'comments']
