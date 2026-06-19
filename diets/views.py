from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated

from accounts.views import CommonResponseAPIView, error_response, success_response

from .models import Food
from .serializers import FoodSerializer


class FoodListCreateView(CommonResponseAPIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request):
        foods = Food.objects.all()

        if request.user.is_authenticated:
            if request.query_params.get('mine') == 'true':
                foods = foods.filter(user=request.user)
            else:
                foods = foods.filter(Q(user__isnull=True) | Q(user=request.user))
        else:
            foods = foods.filter(user__isnull=True)

        search = request.query_params.get('search')
        if search:
            foods = foods.filter(name__icontains=search)

        category = request.query_params.get('category')
        if category:
            foods = foods.filter(category=category)

        serializer = FoodSerializer(foods.order_by('id'), many=True)
        return success_response('음식 목록 조회 성공', serializer.data)

    def post(self, request):
        serializer = FoodSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('음식 추가에 실패했습니다.', serializer.errors)

        food = serializer.save(user=request.user)
        return success_response('음식이 추가되었습니다.', FoodSerializer(food).data, status.HTTP_201_CREATED)


class FoodDetailView(CommonResponseAPIView):
    def get_permissions(self):
        if self.request.method in ['PATCH', 'DELETE']:
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request, food_id):
        foods = Food.objects.all()
        if request.user.is_authenticated:
            foods = foods.filter(Q(user__isnull=True) | Q(user=request.user))
        else:
            foods = foods.filter(user__isnull=True)

        try:
            food = foods.get(id=food_id)
        except Food.DoesNotExist:
            return error_response(
                '음식을 찾을 수 없습니다.',
                {'food_id': ['조회 가능한 음식이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

        return success_response('음식 상세 조회 성공', FoodSerializer(food).data)

    def patch(self, request, food_id):
        try:
            food = Food.objects.get(id=food_id, user=request.user)
        except Food.DoesNotExist:
            return error_response(
                '음식 수정에 실패했습니다.',
                {'food_id': ['수정 가능한 내 음식이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

        serializer = FoodSerializer(food, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response('음식 수정에 실패했습니다.', serializer.errors)

        serializer.save()
        return success_response('음식이 수정되었습니다.', serializer.data)

    def delete(self, request, food_id):
        try:
            food = Food.objects.get(id=food_id, user=request.user)
        except Food.DoesNotExist:
            return error_response(
                '음식 삭제에 실패했습니다.',
                {'food_id': ['삭제 가능한 내 음식이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

        food.delete()
        return success_response('음식이 삭제되었습니다.', None)
