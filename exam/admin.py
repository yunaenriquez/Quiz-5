from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import (
    Exam, Question, QuestionChoice, AnswerKey, CorrectAnswer, 
    ExamSubmission, StudentAnswer, ExamAccess
)


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ['title', 'teacher', 'start_date_time', 'end_date_time', 'max_attempts', 'passing_percentage', 'is_active']
    list_filter = ['is_active', 'access_type', 'teacher', 'start_date_time']
    search_fields = ['title', 'description', 'teacher__email']
    readonly_fields = ['created_at', 'updated_at']
    filter_horizontal = ['allowed_students']


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['exam', 'order', 'question_text_preview', 'marks']
    list_filter = ['exam', 'marks']
    search_fields = ['question_text', 'exam__title']
    
    def question_text_preview(self, obj):
        return obj.question_text[:50] + "..." if len(obj.question_text) > 50 else obj.question_text
    question_text_preview.short_description = 'Question Preview'


@admin.register(QuestionChoice)
class QuestionChoiceAdmin(admin.ModelAdmin):
    list_display = ['question', 'choice_label', 'choice_text_preview']
    list_filter = ['question__exam', 'choice_label']
    search_fields = ['choice_text', 'question__question_text']
    
    def choice_text_preview(self, obj):
        return obj.choice_text[:50] + "..." if len(obj.choice_text) > 50 else obj.choice_text
    choice_text_preview.short_description = 'Choice Preview'


@admin.register(ExamSubmission)
class ExamSubmissionAdmin(admin.ModelAdmin):
    list_display = [
        'student_name', 'exam_title', 'attempt_number', 'status_display', 
        'score_display', 'started_at', 'submitted_at', 'admin_actions'
    ]
    list_filter = ['is_completed', 'auto_submitted', 'exam', 'started_at']
    search_fields = ['student__email', 'student__first_name', 'student__last_name', 'exam__title']
    readonly_fields = ['started_at', 'time_taken', 'percentage']
    actions = ['reset_incomplete_attempts', 'mark_as_completed']
    
    def student_name(self, obj):
        return obj.student.get_full_name()
    student_name.short_description = 'Student'
    
    def exam_title(self, obj):
        return obj.exam.title
    exam_title.short_description = 'Exam'
    
    def status_display(self, obj):
        if obj.is_completed:
            if obj.auto_submitted:
                return format_html('<span style="color: orange;">Auto-submitted</span>')
            else:
                return format_html('<span style="color: green;">Completed</span>')
        else:
            if obj.is_time_up():
                return format_html('<span style="color: red;">Time Expired</span>')
            else:
                return format_html('<span style="color: blue;">In Progress</span>')
    status_display.short_description = 'Status'
    
    def score_display(self, obj):
        if obj.is_completed:
            return f"{obj.score}/{obj.total_marks} ({obj.percentage}%)"
        else:
            return "Not completed"
    score_display.short_description = 'Score'
    
    def admin_actions(self, obj):
        if not obj.is_completed:
            reset_url = reverse('admin:exam_examsubmission_changelist')
            return format_html(
                '<a href="{}?action=reset_incomplete_attempts&_selected_action={}" '
                'onclick="return confirm(\'Reset this incomplete attempt?\');" '
                'style="color: red;">Reset Attempt</a>',
                reset_url, obj.pk
            )
        return "No actions"
    admin_actions.short_description = 'Actions'
    
    def reset_incomplete_attempts(self, request, queryset):
        """Reset incomplete exam attempts"""
        count = 0
        for submission in queryset:
            if not submission.is_completed:
                submission.delete()
                count += 1
        
        self.message_user(
            request, 
            f"Successfully reset {count} incomplete attempt(s). Students can now retry these exams."
        )
    reset_incomplete_attempts.short_description = "Reset selected incomplete attempts"
    
    def mark_as_completed(self, request, queryset):
        """Mark incomplete attempts as completed (emergency use)"""
        count = 0
        for submission in queryset:
            if not submission.is_completed:
                submission.submitted_at = timezone.now()
                submission.is_completed = True
                submission.auto_submitted = True
                submission.time_taken = timezone.timedelta(minutes=submission.exam.duration_minutes)
                
                # Calculate score from existing answers
                score = 0
                for answer in submission.answers.all():
                    if answer.is_correct():
                        score += answer.question.marks
                
                submission.score = score
                submission.save()
                count += 1
        
        self.message_user(
            request, 
            f"Successfully marked {count} attempt(s) as completed."
        )
    mark_as_completed.short_description = "Force complete selected attempts"


@admin.register(StudentAnswer)
class StudentAnswerAdmin(admin.ModelAdmin):
    list_display = ['submission_student', 'submission_exam', 'question_preview', 'selected_choice', 'is_correct_display']
    list_filter = ['submission__exam', 'answered_at']
    search_fields = ['submission__student__email', 'question__question_text']
    
    def submission_student(self, obj):
        return obj.submission.student.get_full_name()
    submission_student.short_description = 'Student'
    
    def submission_exam(self, obj):
        return obj.submission.exam.title
    submission_exam.short_description = 'Exam'
    
    def question_preview(self, obj):
        return f"Q{obj.question.order}: {obj.question.question_text[:30]}..."
    question_preview.short_description = 'Question'
    
    def is_correct_display(self, obj):
        if obj.is_correct():
            return format_html('<span style="color: green;">✓ Correct</span>')
        else:
            return format_html('<span style="color: red;">✗ Incorrect</span>')
    is_correct_display.short_description = 'Result'


@admin.register(AnswerKey)
class AnswerKeyAdmin(admin.ModelAdmin):
    list_display = ['exam', 'created_by', 'created_at']
    list_filter = ['created_at', 'exam__teacher']
    search_fields = ['exam__title', 'created_by__email']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(CorrectAnswer)
class CorrectAnswerAdmin(admin.ModelAdmin):
    list_display = ['answer_key', 'question_preview', 'correct_choice', 'explanation_preview']
    list_filter = ['answer_key__exam']
    search_fields = ['question__question_text', 'explanation']
    
    def question_preview(self, obj):
        return f"Q{obj.question.order}: {obj.question.question_text[:30]}..."
    question_preview.short_description = 'Question'
    
    def explanation_preview(self, obj):
        if obj.explanation:
            return obj.explanation[:50] + "..." if len(obj.explanation) > 50 else obj.explanation
        return "No explanation"
    explanation_preview.short_description = 'Explanation'


@admin.register(ExamAccess)
class ExamAccessAdmin(admin.ModelAdmin):
    list_display = ['exam', 'student', 'granted_by', 'granted_at', 'is_revoked']
    list_filter = ['is_revoked', 'granted_at', 'exam']
    search_fields = ['student__email', 'exam__title', 'granted_by__email']
