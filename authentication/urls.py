from django.urls import path
from .views import (
    CustomLoginView, 
    CustomLogoutView, 
    SignInRedirectView,
    StudentProfileView,
    TeacherProfileView
)

app_name = 'authentication'

urlpatterns = [
    path('signin/', CustomLoginView.as_view(), name='signin'),
    path('logout/', CustomLogoutView.as_view(), name='logout'),
    path('redirect/', SignInRedirectView.as_view(), name='signin_redirect'),
    path('student-profile/', StudentProfileView.as_view(), name='student_profile'),
    path('teacher-profile/', TeacherProfileView.as_view(), name='teacher_profile'),
]