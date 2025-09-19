from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import RedirectView, TemplateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import redirect
from django.db.models import Avg, Sum, F
from django.contrib.auth import logout

# Import exam models for profile analytics
from exam.models import (
    Exam, ExamSubmission, StudentAnswer, Question, QuestionChoice
)


class CustomLoginView(LoginView):
    form_class = AuthenticationForm
    template_name = 'authentication/signin.html'
    redirect_authenticated_user = True
    
    def get_success_url(self):
        user = self.request.user
        
        if user.has_admin_permissions():
            messages.success(self.request, f'Welcome back, {user.get_full_name()}! (Admin)')
            return reverse_lazy('admin:index')
        else:
            role = 'Teacher' if user.is_teacher else 'Student'
            messages.success(self.request, f'Welcome back, {user.get_full_name()}! ({role})')
            return reverse_lazy('exam:dashboard')
    
    def form_invalid(self, form):
        messages.error(self.request, 'Invalid email or password. Please try again.')
        return super().form_invalid(form)
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            messages.info(request, 'You are already signed in.')
            return redirect(self.get_success_url())
        return super().dispatch(request, *args, **kwargs)


class CustomLogoutView(RedirectView):
    
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            user_name = request.user.get_full_name() or request.user.email
            logout(request)
            messages.success(request, f'You have been successfully signed out. See you later, {user_name}!')
        
        return super().get(request, *args, **kwargs)
    
    def post(self, request, *args, **kwargs):
        return self.get(request, *args, **kwargs)


class SignInRedirectView(RedirectView):
    permanent = False
    
    def get_redirect_url(self, *args, **kwargs):
        if self.request.user.is_authenticated:
            user = self.request.user
            if user.has_admin_permissions():
                return reverse_lazy('admin:index')
            else:
                return reverse_lazy('exam:dashboard')
        else:
            return reverse_lazy('authentication:signin')


class TeacherProfileView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'authentication/teacher_profile.html'
    
    def test_func(self):
        return self.request.user.user_type == 'teacher'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        teacher = self.request.user
        
        # Get all exams created by this teacher
        teacher_exams = Exam.objects.filter(teacher=teacher).prefetch_related(
            'submissions', 'questions', 'submissions__answers'
        )
        
        # Overall teaching statistics
        total_exams = teacher_exams.count()
        total_submissions = ExamSubmission.objects.filter(
            exam__teacher=teacher, is_completed=True
        ).count()
        
        # Calculate overall average score across all exams
        completed_submissions = ExamSubmission.objects.filter(
            exam__teacher=teacher, is_completed=True
        )
        
        if completed_submissions.exists():
            overall_avg_score = completed_submissions.aggregate(
                avg_percentage=Avg('percentage')
            )['avg_percentage'] or 0
        else:
            overall_avg_score = 0
        
        # Detailed exam analytics
        exam_analytics = []
        for exam in teacher_exams:
            exam_submissions = exam.submissions.filter(is_completed=True)
            
            # Basic exam stats
            total_attempts = exam_submissions.count()
            
            if total_attempts > 0:
                # Pass/fail analysis
                passed_count = exam_submissions.filter(
                    percentage__gte=exam.passing_percentage
                ).count()
                failed_count = total_attempts - passed_count
                pass_rate = (passed_count / total_attempts) * 100 if total_attempts > 0 else 0
                
                # Score statistics
                avg_score = exam_submissions.aggregate(
                    avg=Avg('percentage')
                )['avg'] or 0
                
                # Time analysis
                avg_time_taken = exam_submissions.aggregate(
                    avg_time=Avg('time_taken')
                )['avg_time']
                
                allocated_time_minutes = exam.duration_minutes
                avg_time_minutes = 0
                time_efficiency = 0
                
                if avg_time_taken:
                    avg_time_minutes = avg_time_taken.total_seconds() / 60
                    time_efficiency = (avg_time_minutes / allocated_time_minutes) * 100 if allocated_time_minutes > 0 else 0
                
                # Question difficulty analysis - find hardest questions
                question_difficulty = []
                for question in exam.questions.all():
                    question_answers = StudentAnswer.objects.filter(
                        submission__exam=exam,
                        submission__is_completed=True,
                        question=question
                    )
                    
                    if question_answers.exists():
                        # Calculate correct answers manually since is_correct() is a method
                        correct_count = 0
                        total_answers = question_answers.count()
                        
                        for answer in question_answers:
                            if answer.is_correct():
                                correct_count += 1
                        
                        success_rate = (correct_count / total_answers) * 100
                        
                        question_difficulty.append({
                            'question': question,
                            'success_rate': success_rate,
                            'total_attempts': total_answers
                        })
                
                # Sort by success rate (ascending = most difficult first)
                question_difficulty.sort(key=lambda x: x['success_rate'])
                
            else:
                # No submissions yet
                passed_count = failed_count = 0
                pass_rate = avg_score = avg_time_minutes = time_efficiency = 0
                question_difficulty = []
            
            exam_analytics.append({
                'exam': exam,
                'total_attempts': total_attempts,
                'passed_count': passed_count,
                'failed_count': failed_count,
                'pass_rate': pass_rate,
                'avg_score': avg_score,
                'avg_time_minutes': avg_time_minutes,
                'allocated_time_minutes': allocated_time_minutes,
                'time_efficiency': time_efficiency,
                'question_difficulty': question_difficulty[:3],  # Top 3 most difficult
                'total_questions': exam.questions.count(),
            })
        
        context.update({
            'teacher': teacher,
            'total_exams': total_exams,
            'total_submissions': total_submissions,
            'overall_avg_score': overall_avg_score,
            'exam_analytics': exam_analytics,
        })
        
        return context


class StudentProfileView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'authentication/student_profile.html'
    
    def test_func(self):
        return self.request.user.user_type == 'student'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        student = self.request.user
        
        # Get all exam submissions for this student
        all_submissions = ExamSubmission.objects.filter(
            student=student,
            is_completed=True
        ).select_related('exam').order_by('-submitted_at')
        
        # Calculate average score
        if total_exams_taken > 0:
            avg_score = all_submissions.aggregate(
                avg=Avg('percentage')
            )['avg']
            avg_score = round(avg_score, 2) if avg_score else 0
        else:
            avg_score = 0
        
        # Get recent exam history (last 10)
        recent_submissions = all_submissions[:10]
        
        
        # Get performance by exam
        exam_performance = []
        for submission in recent_submissions:
            exam_performance.append({
                'exam': submission.exam,
                'submission': submission,
                'result_status': submission.get_result_status(),
                'badge_class': submission.get_result_badge_class(),
            })
        
        # Get grade distribution
        grade_ranges = [
            ('A (90-100%)', all_submissions.filter(percentage__gte=90).count()),
            ('B (80-89%)', all_submissions.filter(percentage__gte=80, percentage__lt=90).count()),
            ('C (70-79%)', all_submissions.filter(percentage__gte=70, percentage__lt=80).count()),
            ('D (60-69%)', all_submissions.filter(percentage__gte=60, percentage__lt=70).count()),
            ('F (0-59%)', all_submissions.filter(percentage__lt=60).count()),
        ]
        
        context.update({
            'student': student,
            'avg_score': avg_score,
            'recent_submissions': recent_submissions,
            'exam_performance': exam_performance,
            'grade_ranges': grade_ranges,
        })
        
        return context
    
    def handle_no_permission(self):
        messages.error(self.request, 'Access denied.')
        return redirect('exam:dashboard')
