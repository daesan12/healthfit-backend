from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Prefetch
from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated

from accounts.views import CommonResponseAPIView, error_response, success_response
from config.pagination import paginate_data

from .models import Comment, Like, Post, SharedPostSave
from .serializers import (
    CommentSerializer,
    PostDetailSerializer,
    PostSerializer,
    PublicProfileInfoSerializer,
    PublicUserSerializer,
)
from .services import (
    SharedSnapshotError,
    copy_saved_meal_from_snapshot,
    copy_workout_routine_from_snapshot,
)


def post_queryset(request=None):
    queryset = Post.objects.select_related(
        'user',
        'shared_saved_meal',
        'shared_workout_routine',
    ).prefetch_related('comments__user', 'likes')
    if request is not None and request.user.is_authenticated:
        queryset = queryset.prefetch_related(Prefetch(
            'shared_saves',
            queryset=SharedPostSave.objects.filter(user=request.user),
            to_attr='viewer_shared_saves',
        ))
    return queryset


class PublicProfileView(CommonResponseAPIView):
    permission_classes = [AllowAny]

    def get(self, request, user_id):
        User = get_user_model()
        try:
            user = User.objects.select_related('profile').get(pk=user_id)
        except User.DoesNotExist:
            return error_response(
                '공개 프로필을 찾을 수 없습니다.',
                {'user_id': ['존재하지 않는 사용자입니다.']},
                status.HTTP_404_NOT_FOUND,
            )

        profile = getattr(user, 'profile', None)
        posts = post_queryset(request).filter(user=user).order_by('-created_at', '-id')
        data = {
            'user': PublicUserSerializer(user).data,
            'profile': PublicProfileInfoSerializer(profile).data if profile else None,
            'post_count': posts.count(),
            'posts': PostSerializer(posts, many=True, context={'request': request}).data,
            'representative_saved_meal': None,
            'representative_workout_routine': None,
        }
        return success_response('사용자 공개 프로필 조회 성공', data)


class PostListCreateView(CommonResponseAPIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request):
        posts = post_queryset(request).order_by('-created_at', '-id')

        search = request.query_params.get('search')
        if search:
            posts = posts.filter(Q(title__icontains=search) | Q(content__icontains=search))

        author = request.query_params.get('author')
        if author:
            posts = posts.filter(user__username__icontains=author)

        category = request.query_params.get('category')
        if category:
            posts = posts.filter(category=category)

        data = paginate_data(
            request,
            posts,
            PostSerializer,
            context={'request': request},
        )
        return success_response('게시글 목록 조회 성공', data)

    def post(self, request):
        serializer = PostSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return error_response('게시글 작성에 실패했습니다.', serializer.errors)

        post = serializer.save(user=request.user)
        return success_response(
            '게시글이 작성되었습니다.',
            PostDetailSerializer(post, context={'request': request}).data,
            status.HTTP_201_CREATED,
        )


class PostDetailView(CommonResponseAPIView):
    def get_permissions(self):
        if self.request.method in ['PATCH', 'DELETE']:
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request, post_id):
        try:
            post = post_queryset(request).get(pk=post_id)
        except Post.DoesNotExist:
            return error_response(
                '게시글을 찾을 수 없습니다.',
                {'post_id': ['조회 가능한 게시글이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

        serializer = PostDetailSerializer(post, context={'request': request})
        return success_response('게시글 상세 조회 성공', serializer.data)

    def get_owned_post(self, request, post_id, message):
        try:
            return post_queryset(request).get(pk=post_id, user=request.user)
        except Post.DoesNotExist:
            return error_response(
                message,
                {'post_id': ['수정 또는 삭제 가능한 내 게시글이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

    def patch(self, request, post_id):
        post = self.get_owned_post(request, post_id, '게시글 수정에 실패했습니다.')
        if not isinstance(post, Post):
            return post

        serializer = PostSerializer(post, data=request.data, partial=True, context={'request': request})
        if not serializer.is_valid():
            return error_response('게시글 수정에 실패했습니다.', serializer.errors)

        serializer.save()
        return success_response('게시글이 수정되었습니다.', serializer.data)

    def delete(self, request, post_id):
        post = self.get_owned_post(request, post_id, '게시글 삭제에 실패했습니다.')
        if not isinstance(post, Post):
            return post

        post.delete()
        return success_response('게시글이 삭제되었습니다.', None)


class CommentCreateView(CommonResponseAPIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request, post_id):
        if not Post.objects.filter(pk=post_id).exists():
            return error_response(
                '댓글 목록 조회에 실패했습니다.',
                {'post_id': ['댓글을 조회할 게시글이 없습니다.']},
                status.HTTP_404_NOT_FOUND,
            )
        comments = Comment.objects.filter(post_id=post_id).select_related('user').order_by(
            'created_at', 'id'
        )
        data = paginate_data(request, comments, CommentSerializer)
        return success_response('댓글 목록 조회 성공', data)

    def post(self, request, post_id):
        try:
            post = Post.objects.get(pk=post_id)
        except Post.DoesNotExist:
            return error_response(
                '댓글 작성에 실패했습니다.',
                {'post_id': ['댓글을 작성할 게시글이 없습니다.']},
                status.HTTP_404_NOT_FOUND,
            )

        serializer = CommentSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('댓글 작성에 실패했습니다.', serializer.errors)

        comment = serializer.save(user=request.user, post=post)
        return success_response(
            '댓글이 작성되었습니다.',
            CommentSerializer(comment).data,
            status.HTTP_201_CREATED,
        )


class CommentDetailView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def get_comment(self, request, comment_id, message):
        try:
            return Comment.objects.select_related('user', 'post').get(
                pk=comment_id,
                user=request.user,
            )
        except Comment.DoesNotExist:
            return error_response(
                message,
                {'comment_id': ['수정 또는 삭제 가능한 내 댓글이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

    def patch(self, request, comment_id):
        comment = self.get_comment(request, comment_id, '댓글 수정에 실패했습니다.')
        if not isinstance(comment, Comment):
            return comment

        serializer = CommentSerializer(comment, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response('댓글 수정에 실패했습니다.', serializer.errors)

        serializer.save()
        return success_response('댓글이 수정되었습니다.', serializer.data)

    def delete(self, request, comment_id):
        comment = self.get_comment(request, comment_id, '댓글 삭제에 실패했습니다.')
        if not isinstance(comment, Comment):
            return comment

        comment.delete()
        return success_response('댓글이 삭제되었습니다.', None)


class LikeToggleView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, post_id):
        try:
            post = Post.objects.get(pk=post_id)
        except Post.DoesNotExist:
            return error_response(
                '좋아요 상태 변경에 실패했습니다.',
                {'post_id': ['좋아요를 변경할 게시글이 없습니다.']},
                status.HTTP_404_NOT_FOUND,
            )

        like, created = Like.objects.get_or_create(user=request.user, post=post)
        if created:
            is_liked = True
        else:
            like.delete()
            is_liked = False

        data = {
            'post_id': post.id,
            'is_liked': is_liked,
            'like_count': post.likes.count(),
        }
        return success_response('좋아요 상태가 변경되었습니다.', data)


class SaveSharedMealView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, post_id):
        try:
            post = Post.objects.get(pk=post_id)
        except Post.DoesNotExist:
            return error_response(
                '공유 식단 저장에 실패했습니다.',
                {'post_id': ['존재하지 않는 게시글입니다.']},
                status.HTTP_404_NOT_FOUND,
            )
        if post.category != 'diet' or not post.shared_saved_meal_snapshot:
            return error_response(
                '공유 식단 저장에 실패했습니다.',
                {'shared_saved_meal': ['이 게시글에는 저장할 공유 식단이 없습니다.']},
            )

        with transaction.atomic():
            existing = SharedPostSave.objects.filter(
                user=request.user,
                post=post,
                save_type=SharedPostSave.SAVED_MEAL,
            ).select_related('saved_meal').first()
            if existing and existing.saved_meal_id:
                return success_response(
                    '이미 내 저장 식단에 추가된 공유 식단입니다.',
                    {
                        'saved_meal_id': existing.saved_meal_id,
                        'name': existing.saved_meal.name,
                        'already_saved': True,
                    },
                )
            if existing:
                existing.delete()

            try:
                saved_meal = copy_saved_meal_from_snapshot(
                    post.shared_saved_meal_snapshot,
                    request.user,
                )
            except SharedSnapshotError as exc:
                return error_response('공유 식단 저장에 실패했습니다.', exc.errors)

            SharedPostSave.objects.create(
                user=request.user,
                post=post,
                save_type=SharedPostSave.SAVED_MEAL,
                saved_meal=saved_meal,
            )

        return success_response(
            '공유 식단이 내 저장 식단에 추가되었습니다.',
            {'saved_meal_id': saved_meal.id, 'name': saved_meal.name, 'already_saved': False},
            status.HTTP_201_CREATED,
        )


class SaveSharedRoutineView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, post_id):
        try:
            post = Post.objects.get(pk=post_id)
        except Post.DoesNotExist:
            return error_response(
                '공유 루틴 저장에 실패했습니다.',
                {'post_id': ['존재하지 않는 게시글입니다.']},
                status.HTTP_404_NOT_FOUND,
            )
        if post.category != 'workout' or not post.shared_workout_routine_snapshot:
            return error_response(
                '공유 루틴 저장에 실패했습니다.',
                {'shared_workout_routine': ['이 게시글에는 저장할 공유 루틴이 없습니다.']},
            )

        with transaction.atomic():
            existing = SharedPostSave.objects.filter(
                user=request.user,
                post=post,
                save_type=SharedPostSave.WORKOUT_ROUTINE,
            ).select_related('workout_routine').first()
            if existing and existing.workout_routine_id:
                return success_response(
                    '이미 내 운동 루틴에 추가된 공유 루틴입니다.',
                    {
                        'routine_id': existing.workout_routine_id,
                        'name': existing.workout_routine.name,
                        'already_saved': True,
                    },
                )
            if existing:
                existing.delete()

            try:
                routine = copy_workout_routine_from_snapshot(
                    post.shared_workout_routine_snapshot,
                    request.user,
                )
            except SharedSnapshotError as exc:
                return error_response('공유 루틴 저장에 실패했습니다.', exc.errors)

            SharedPostSave.objects.create(
                user=request.user,
                post=post,
                save_type=SharedPostSave.WORKOUT_ROUTINE,
                workout_routine=routine,
            )

        return success_response(
            '공유 루틴이 내 운동 루틴에 추가되었습니다.',
            {'routine_id': routine.id, 'name': routine.name, 'already_saved': False},
            status.HTTP_201_CREATED,
        )
