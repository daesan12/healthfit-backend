from django.contrib.auth import get_user_model
from rest_framework import serializers

from accounts.models import Profile
from diets.models import SavedMeal
from workouts.models import WorkoutRoutine

from .models import Comment, Post, SharedPostSave
from .services import build_saved_meal_snapshot, build_workout_routine_snapshot


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ['id', 'username']


class PublicUserSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(source='date_joined', read_only=True)

    class Meta:
        model = get_user_model()
        fields = ['id', 'username', 'created_at']


class PublicProfileInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ['workout_goal']


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
    shared_saved_meal_id = serializers.PrimaryKeyRelatedField(
        source='shared_saved_meal',
        queryset=SavedMeal.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
    )
    shared_workout_routine_id = serializers.PrimaryKeyRelatedField(
        source='shared_workout_routine',
        queryset=WorkoutRoutine.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
    )
    comment_count = serializers.SerializerMethodField()
    like_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    shared_type = serializers.SerializerMethodField()
    shared_saved_meal = serializers.SerializerMethodField()
    shared_workout_routine = serializers.SerializerMethodField()
    viewer_save_status = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            'id',
            'author',
            'title',
            'content',
            'category',
            'shared_saved_meal_id',
            'shared_workout_routine_id',
            'shared_type',
            'shared_saved_meal',
            'shared_workout_routine',
            'viewer_save_status',
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

    def get_shared_type(self, obj):
        if obj.shared_saved_meal_snapshot:
            return SharedPostSave.SAVED_MEAL
        if obj.shared_workout_routine_snapshot:
            return SharedPostSave.WORKOUT_ROUTINE
        return None

    def get_shared_saved_meal(self, obj):
        return obj.shared_saved_meal_snapshot

    def get_shared_workout_routine(self, obj):
        return obj.shared_workout_routine_snapshot

    def get_viewer_save_status(self, obj):
        request = self.context.get('request')
        if request is None or not request.user.is_authenticated:
            return None

        shared_type = self.get_shared_type(obj)
        saves = getattr(obj, 'viewer_shared_saves', None)
        if saves is None:
            saves = obj.shared_saves.filter(user=request.user, save_type=shared_type)
        shared_save = next(
            (item for item in saves if item.save_type == shared_type),
            None,
        )
        return {
            'saved': bool(
                shared_save
                and (shared_save.saved_meal_id or shared_save.workout_routine_id)
            ),
            'saved_meal_id': shared_save.saved_meal_id if shared_save else None,
            'workout_routine_id': shared_save.workout_routine_id if shared_save else None,
        }

    def validate(self, attrs):
        request = self.context.get('request')
        instance = self.instance
        category = attrs.get('category', instance.category if instance else None)
        meal_supplied = 'shared_saved_meal' in attrs
        routine_supplied = 'shared_workout_routine' in attrs
        meal = attrs.get(
            'shared_saved_meal',
            instance.shared_saved_meal if instance else None,
        )
        routine = attrs.get(
            'shared_workout_routine',
            instance.shared_workout_routine if instance else None,
        )
        errors = {}

        if meal and request and meal.user_id != request.user.id:
            errors['shared_saved_meal_id'] = ['본인의 저장 식단만 공유할 수 있습니다.']
        if routine and request and routine.user_id != request.user.id:
            errors['shared_workout_routine_id'] = ['본인의 운동 루틴만 공유할 수 있습니다.']

        if category == 'diet':
            if routine_supplied and routine is not None:
                errors['shared_workout_routine_id'] = ['식단 게시글에는 운동 루틴을 첨부할 수 없습니다.']
            attrs['shared_workout_routine'] = None
        elif category == 'workout':
            if meal_supplied and meal is not None:
                errors['shared_saved_meal_id'] = ['운동 게시글에는 저장 식단을 첨부할 수 없습니다.']
            attrs['shared_saved_meal'] = None
        elif category == 'free':
            if meal_supplied and meal is not None:
                errors['shared_saved_meal_id'] = ['자유 게시글에는 저장 식단을 첨부할 수 없습니다.']
            if routine_supplied and routine is not None:
                errors['shared_workout_routine_id'] = ['자유 게시글에는 운동 루틴을 첨부할 수 없습니다.']
            attrs['shared_saved_meal'] = None
            attrs['shared_workout_routine'] = None

        if meal is not None and routine is not None and category not in ['diet', 'workout']:
            errors['shared_item'] = ['게시글에는 공유 항목을 하나만 첨부할 수 있습니다.']
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        post = super().create(validated_data)
        self._sync_snapshots(post, force=True)
        return post

    def update(self, instance, validated_data):
        previous_category = instance.category
        meal_supplied = 'shared_saved_meal_id' in self.initial_data
        routine_supplied = 'shared_workout_routine_id' in self.initial_data
        post = super().update(instance, validated_data)
        self._sync_snapshots(
            post,
            force=False,
            meal_changed=meal_supplied or previous_category != post.category,
            routine_changed=routine_supplied or previous_category != post.category,
        )
        return post

    def _sync_snapshots(
        self,
        post,
        force=False,
        meal_changed=False,
        routine_changed=False,
    ):
        update_fields = []
        if post.category == 'diet':
            if force or meal_changed:
                post.shared_saved_meal_snapshot = (
                    build_saved_meal_snapshot(post.shared_saved_meal)
                    if post.shared_saved_meal_id
                    else None
                )
                update_fields.append('shared_saved_meal_snapshot')
            if post.shared_workout_routine_snapshot is not None:
                post.shared_workout_routine_snapshot = None
                update_fields.append('shared_workout_routine_snapshot')
        elif post.category == 'workout':
            if force or routine_changed:
                post.shared_workout_routine_snapshot = (
                    build_workout_routine_snapshot(post.shared_workout_routine)
                    if post.shared_workout_routine_id
                    else None
                )
                update_fields.append('shared_workout_routine_snapshot')
            if post.shared_saved_meal_snapshot is not None:
                post.shared_saved_meal_snapshot = None
                update_fields.append('shared_saved_meal_snapshot')
        else:
            if post.shared_saved_meal_snapshot is not None:
                post.shared_saved_meal_snapshot = None
                update_fields.append('shared_saved_meal_snapshot')
            if post.shared_workout_routine_snapshot is not None:
                post.shared_workout_routine_snapshot = None
                update_fields.append('shared_workout_routine_snapshot')

        if update_fields:
            post.save(update_fields=[*set(update_fields), 'updated_at'])


class PostDetailSerializer(PostSerializer):
    comments = CommentSerializer(many=True, read_only=True)

    class Meta(PostSerializer.Meta):
        fields = [*PostSerializer.Meta.fields, 'comments']
