from urllib.parse import urlsplit

from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination


class PaginationError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__('Pagination request is invalid.')


class HealthFitPageNumberPagination(PageNumberPagination):
    page_size = 20
    page_query_param = 'page'
    page_size_query_param = 'page_size'
    max_page_size = 100
    last_page_strings = ()

    def get_page_size(self, request):
        value = request.query_params.get(self.page_size_query_param)
        if value is None:
            return self.page_size
        try:
            page_size = int(value)
        except (TypeError, ValueError) as exc:
            raise PaginationError({'page_size': ['page_size는 1 이상의 정수여야 합니다.']}) from exc
        if page_size < 1:
            raise PaginationError({'page_size': ['page_size는 1 이상의 정수여야 합니다.']})
        return min(page_size, self.max_page_size)

    def paginate_queryset(self, queryset, request, view=None):
        try:
            return super().paginate_queryset(queryset, request, view)
        except NotFound as exc:
            raise PaginationError({'page': ['존재하는 페이지 번호를 입력해주세요.']}) from exc

    def get_pagination_data(self, results):
        return {
            'count': self.page.paginator.count,
            'page': self.page.number,
            'page_size': self.page.paginator.per_page,
            'total_pages': self.page.paginator.num_pages,
            'next': self._relative_link(self.get_next_link()),
            'previous': self._relative_link(self.get_previous_link()),
            'has_next': self.page.has_next(),
            'has_previous': self.page.has_previous(),
            'results': results,
        }

    def _relative_link(self, link):
        if link is None:
            return None
        parsed = urlsplit(link)
        return f'{parsed.path}?{parsed.query}' if parsed.query else parsed.path


def paginate_data(request, queryset, serializer_class, *, context=None):
    paginator = HealthFitPageNumberPagination()
    page = paginator.paginate_queryset(queryset, request)
    serializer = serializer_class(page, many=True, context=context or {})
    return paginator.get_pagination_data(serializer.data)
