from django.urls import path
from .views import (
   DashboardView,
   TeacherDashboardView,
   StudentDashboardView,
   ExamCreateView,
   QuestionManagementView,
   ExamDetailView,
   ExamUpdateView,
   StudentExamView,
   StartExamView,
   TakeExamView,
   ExamResultView
)


app_name = 'exam'


urlpatterns = [
   path('', DashboardView.as_view(), name='dashboard'),
   path('teacher-dashboard/', TeacherDashboardView.as_view(), name='teacher_dashboard'),
   path('student-dashboard/', StudentDashboardView.as_view(), name='student_dashboard'),
   path('create/', ExamCreateView.as_view(), name='create_exam'),
   path('<int:pk>/', ExamDetailView.as_view(), name='exam_detail'),
   path('<int:pk>/edit/', ExamUpdateView.as_view(), name='edit_exam'),
   path('<int:exam_id>/questions/', QuestionManagementView.as_view(), name='manage_questions'),


   # Student exam taking URLs
   path('<int:pk>/student/', StudentExamView.as_view(), name='student_exam'),
   path('<int:pk>/start/', StartExamView.as_view(), name='start_exam'),
   path('take/<int:submission_id>/', TakeExamView.as_view(), name='take_exam'),
   path('result/<int:submission_id>/', ExamResultView.as_view(), name='exam_result'),
]