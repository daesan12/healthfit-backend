from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated

from accounts.views import CommonResponseAPIView, error_response, success_response

from .models import Comment, Like, Post
from .serializers import CommentSerializer, PostDetailSerializer, PostSerializer


def post_queryset():
    return Post.objects.select_related('user').prefetch_related('comments__user', 'likes')


class PostListCreateView(CommonResponseAPIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request):
        posts = post_queryset().order_by('-created_at', '-id')

        search = request.query_params.get('search')
        if search:
            posts = posts.filter(Q(title__icontains=search) | Q(content__icontains=search))

        author = request.query_params.get('author')
        if author:
            posts = posts.filter(user__username__icontains=author)

        category = request.query_params.get('category')
        if category:
            posts = posts.filter(category=category)

        page_text = request.query_params.get('page', '1')
        try:
            page = int(page_text)
            if page < 1:
                raise ValueError
        except ValueError:
            return error_response(
                '게시글 목록 조회에 실패했습니다.',
                {'page': ['페이지 번호는 1 이상의 정수여야 합니다.']},
            )

        count = posts.count()
        page_size = 10
        offset = (page - 1) * page_size
        serializer = PostSerializer(
            posts[offset:offset + page_size],
            many=True,
            context={'request': request},
        )
        data = {
            'count': count,
            'page': page,
            'page_size': page_size,
            'results': serializer.data,
        }
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
            post = post_queryset().get(pk=post_id)
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
            return post_queryset().get(pk=post_id, user=request.user)
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
    permission_classes = [IsAuthenticated]

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
