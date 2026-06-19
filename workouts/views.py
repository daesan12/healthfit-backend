from rest_framework import status
from rest_framework.permissions import AllowAny

from accounts.views import CommonResponseAPIView, error_response, success_response

from .models import Exercise
from .serializers import ExerciseSerializer


class ExerciseListView(CommonResponseAPIView):
    permission_classes = [AllowAny]

    def get(self, request):
        exercises = Exercise.objects.all()

        search = request.query_params.get('search')
        if search:
            exercises = exercises.filter(name__icontains=search)

        body_part = request.query_params.get('body_part')
        if body_part:
            exercises = exercises.filter(body_parts__icontains=body_part)

        equipment = request.query_params.get('equipment')
        if equipment:
            exercises = exercises.filter(equipments__icontains=equipment)

        target_muscle = request.query_params.get('target_muscle')
        if target_muscle:
            exercises = exercises.filter(target_muscles__icontains=target_muscle)

        serializer = ExerciseSerializer(exercises.order_by('id'), many=True)
        return success_response('운동 목록 조회 성공', serializer.data)


class ExerciseDetailView(CommonResponseAPIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            exercise = Exercise.objects.get(pk=pk)
        except Exercise.DoesNotExist:
            return error_response(
                '운동을 찾을 수 없습니다.',
                {'pk': ['조회 가능한 운동이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

        return success_response('운동 상세 조회 성공', ExerciseSerializer(exercise).data)
