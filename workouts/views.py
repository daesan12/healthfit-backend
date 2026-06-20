from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated

from accounts.views import CommonResponseAPIView, error_response, success_response

from .models import Exercise, RoutineItem, WorkoutLog, WorkoutRoutine
from .serializers import (
    ExerciseSerializer,
    RoutineItemSerializer,
    WorkoutLogSerializer,
    WorkoutRoutineSerializer,
)


def visible_exercises(user):
    if user.is_authenticated:
        return Exercise.objects.filter(Q(user__isnull=True) | Q(user=user))
    return Exercise.objects.filter(user__isnull=True)


class ExerciseListView(CommonResponseAPIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request):
        exercises = visible_exercises(request.user)

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

    def post(self, request):
        serializer = ExerciseSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('운동 추가에 실패했습니다.', serializer.errors)

        exercise = serializer.save(user=request.user)
        return success_response(
            '운동이 추가되었습니다.',
            ExerciseSerializer(exercise).data,
            status.HTTP_201_CREATED,
        )


class ExerciseDetailView(CommonResponseAPIView):
    def get_permissions(self):
        if self.request.method in ['PATCH', 'DELETE']:
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request, pk):
        try:
            exercise = visible_exercises(request.user).get(pk=pk)
        except Exercise.DoesNotExist:
            return error_response(
                '운동을 찾을 수 없습니다.',
                {'pk': ['조회 가능한 운동이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

        return success_response('운동 상세 조회 성공', ExerciseSerializer(exercise).data)

    def patch(self, request, pk):
        try:
            exercise = Exercise.objects.get(pk=pk, user=request.user)
        except Exercise.DoesNotExist:
            return error_response(
                '운동 수정에 실패했습니다.',
                {'pk': ['수정 가능한 내 운동이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

        serializer = ExerciseSerializer(exercise, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response('운동 수정에 실패했습니다.', serializer.errors)

        serializer.save()
        return success_response('운동이 수정되었습니다.', serializer.data)

    def delete(self, request, pk):
        try:
            exercise = Exercise.objects.get(pk=pk, user=request.user)
        except Exercise.DoesNotExist:
            return error_response(
                '운동 삭제에 실패했습니다.',
                {'pk': ['삭제 가능한 내 운동이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

        exercise.delete()
        return success_response('운동이 삭제되었습니다.', None)


class WorkoutRoutineListCreateView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        routines = WorkoutRoutine.objects.filter(user=request.user).prefetch_related('items__exercise')
        serializer = WorkoutRoutineSerializer(routines.order_by('-id'), many=True)
        return success_response('운동 루틴 목록 조회 성공', serializer.data)

    def post(self, request):
        serializer = WorkoutRoutineSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('운동 루틴 생성에 실패했습니다.', serializer.errors)

        routine = serializer.save(user=request.user)
        return success_response(
            '운동 루틴이 생성되었습니다.',
            WorkoutRoutineSerializer(routine).data,
            status.HTTP_201_CREATED,
        )


class WorkoutRoutineDetailView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def get_routine(self, request, routine_id, message):
        try:
            return WorkoutRoutine.objects.prefetch_related('items__exercise').get(
                pk=routine_id,
                user=request.user,
            )
        except WorkoutRoutine.DoesNotExist:
            return error_response(
                message,
                {'routine_id': ['조회 가능한 내 운동 루틴이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

    def get(self, request, routine_id):
        routine = self.get_routine(request, routine_id, '운동 루틴 상세 조회에 실패했습니다.')
        if not isinstance(routine, WorkoutRoutine):
            return routine

        return success_response('운동 루틴 상세 조회 성공', WorkoutRoutineSerializer(routine).data)

    def patch(self, request, routine_id):
        routine = self.get_routine(request, routine_id, '운동 루틴 수정에 실패했습니다.')
        if not isinstance(routine, WorkoutRoutine):
            return routine

        serializer = WorkoutRoutineSerializer(routine, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response('운동 루틴 수정에 실패했습니다.', serializer.errors)

        serializer.save()
        return success_response('운동 루틴이 수정되었습니다.', serializer.data)

    def delete(self, request, routine_id):
        routine = self.get_routine(request, routine_id, '운동 루틴 삭제에 실패했습니다.')
        if not isinstance(routine, WorkoutRoutine):
            return routine

        routine.delete()
        return success_response('운동 루틴이 삭제되었습니다.', None)


class RoutineItemCreateView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, routine_id):
        try:
            routine = WorkoutRoutine.objects.get(pk=routine_id, user=request.user)
        except WorkoutRoutine.DoesNotExist:
            return error_response(
                '루틴 항목 추가에 실패했습니다.',
                {'routine_id': ['항목을 추가할 수 있는 내 운동 루틴이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

        serializer = RoutineItemSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return error_response('루틴 항목 추가에 실패했습니다.', serializer.errors)

        item = serializer.save(routine=routine)
        return success_response(
            '루틴 항목이 추가되었습니다.',
            RoutineItemSerializer(item).data,
            status.HTTP_201_CREATED,
        )


class RoutineItemDetailView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def get_item(self, request, routine_item_id, message):
        try:
            return RoutineItem.objects.select_related('exercise', 'routine').get(
                pk=routine_item_id,
                routine__user=request.user,
            )
        except RoutineItem.DoesNotExist:
            return error_response(
                message,
                {'routine_item_id': ['수정 또는 삭제 가능한 내 루틴 항목이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

    def patch(self, request, routine_item_id):
        item = self.get_item(request, routine_item_id, '루틴 항목 수정에 실패했습니다.')
        if not isinstance(item, RoutineItem):
            return item

        serializer = RoutineItemSerializer(
            item,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        if not serializer.is_valid():
            return error_response('루틴 항목 수정에 실패했습니다.', serializer.errors)

        serializer.save()
        return success_response('루틴 항목이 수정되었습니다.', serializer.data)

    def delete(self, request, routine_item_id):
        item = self.get_item(request, routine_item_id, '루틴 항목 삭제에 실패했습니다.')
        if not isinstance(item, RoutineItem):
            return item

        item.delete()
        return success_response('루틴 항목이 삭제되었습니다.', None)


class WorkoutLogListCreateView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        logs = WorkoutLog.objects.filter(user=request.user).select_related(
            'exercise', 'routine'
        ).prefetch_related('sets')

        date = request.query_params.get('date')
        if date:
            logs = logs.filter(workout_date=date)

        start_date = request.query_params.get('start_date')
        if start_date:
            logs = logs.filter(workout_date__gte=start_date)

        end_date = request.query_params.get('end_date')
        if end_date:
            logs = logs.filter(workout_date__lte=end_date)

        routine_id = request.query_params.get('routine_id')
        if routine_id:
            logs = logs.filter(routine_id=routine_id)

        workout_id = request.query_params.get('workout_id') or request.query_params.get('exercise_id')
        if workout_id:
            logs = logs.filter(exercise_id=workout_id)

        serializer = WorkoutLogSerializer(logs.order_by('-workout_date', '-id'), many=True)
        return success_response('운동 기록 목록 조회 성공', serializer.data)

    def post(self, request):
        serializer = WorkoutLogSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return error_response('운동 기록 등록에 실패했습니다.', serializer.errors)

        log = serializer.save(user=request.user)
        return success_response(
            '운동 기록이 등록되었습니다.',
            WorkoutLogSerializer(log).data,
            status.HTTP_201_CREATED,
        )


class WorkoutLogDetailView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def get_log(self, request, log_id, message):
        try:
            return WorkoutLog.objects.select_related('exercise', 'routine').prefetch_related('sets').get(
                pk=log_id,
                user=request.user,
            )
        except WorkoutLog.DoesNotExist:
            return error_response(
                message,
                {'log_id': ['조회 가능한 내 운동 기록이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

    def get(self, request, log_id):
        log = self.get_log(request, log_id, '운동 기록 상세 조회에 실패했습니다.')
        if not isinstance(log, WorkoutLog):
            return log

        return success_response('운동 기록 상세 조회 성공', WorkoutLogSerializer(log).data)

    def patch(self, request, log_id):
        log = self.get_log(request, log_id, '운동 기록 수정에 실패했습니다.')
        if not isinstance(log, WorkoutLog):
            return log

        serializer = WorkoutLogSerializer(
            log,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        if not serializer.is_valid():
            return error_response('운동 기록 수정에 실패했습니다.', serializer.errors)

        serializer.save()
        return success_response('운동 기록이 수정되었습니다.', serializer.data)

    def delete(self, request, log_id):
        log = self.get_log(request, log_id, '운동 기록 삭제에 실패했습니다.')
        if not isinstance(log, WorkoutLog):
            return log

        log.delete()
        return success_response('운동 기록이 삭제되었습니다.', None)
