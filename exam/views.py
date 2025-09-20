from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, CreateView, DetailView, UpdateView, TemplateView
from django.views import View
from django.contrib import messages
from django.db.models import Count, Q, F, Avg, Sum
from django.utils import timezone
from django.urls import reverse_lazy, reverse
from django.db import transaction
from django.contrib.auth import get_user_model
from django import forms
from django.http import JsonResponse
import random
import json

from exam.forms import ExamForm
from .models import (
    Exam, Question, QuestionChoice, AnswerKey, CorrectAnswer,
    ExamSubmission, StudentAnswer
)

User = get_user_model()


class DashboardView(LoginRequiredMixin, ListView):
    template_name = 'exam/dashboard.html'
    context_object_name = 'exams'
    paginate_by = 12

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('authentication:signin')

        if request.user.is_teacher:
            return TeacherDashboardView.as_view()(request, *args, **kwargs)
        elif request.user.is_student:
            return StudentDashboardView.as_view()(request, *args, **kwargs)
        else:
            messages.error(request, 'Access denied. Invalid user role.')
            return redirect('authentication:signin')


class TeacherDashboardView(LoginRequiredMixin, ListView):
    model = Exam
    template_name = 'exam/teacher_dashboard.html'
    context_object_name = 'exams'
    paginate_by = 12

    def get_queryset(self):
        from django.db.models import Case, When, IntegerField

        now = timezone.now()

        # Get all exams created by this teacher with priority ordering
        queryset = Exam.objects.filter(
            teacher=self.request.user
        ).annotate(
            priority=Case(
                # Active exams (currently running) - Priority 1
                When(
                    is_active=True,
                    start_date_time__lte=now,
                    end_date_time__gte=now,
                    then=1
                ),
                # Upcoming exams - Priority 2
                When(
                    is_active=True,
                    start_date_time__gt=now,
                    then=2
                ),
                # Expired exams - Priority 3
                When(
                    end_date_time__lt=now,
                    then=3
                ),
                # Disabled exams - Priority 4
                When(
                    is_active=False,
                    then=4
                ),
                default=4,
                output_field=IntegerField()
            )
        ).order_by('priority', 'start_date_time')

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user_role'] = 'Teacher'

        now = timezone.now()
        queryset = Exam.objects.filter(teacher=self.request.user)

        context['total_exams'] = queryset.count()

        # Count exams by their actual status (not just is_active field)
        context['active_exams'] = queryset.filter(
            is_active=True,
            start_date_time__lte=now,
            end_date_time__gte=now
        ).count()

        context['upcoming_exams'] = queryset.filter(
            is_active=True,
            start_date_time__gt=now
        ).count()

        context['expired_exams'] = queryset.filter(
            end_date_time__lt=now
        ).count()

        context['disabled_exams'] = queryset.filter(
            is_active=False
        ).count()

        return context


class StudentDashboardView(LoginRequiredMixin, ListView):
    model = Exam
    template_name = 'exam/student_dashboard.html'
    context_object_name = 'exams'
    paginate_by = 12

    def get_queryset(self):
        from django.db.models import Case, When, IntegerField

        user = self.request.user
        now = timezone.now()

        # Get all exams the student has access to
        base_queryset = Exam.objects.filter(
            Q(access_type='all_students') |
            Q(access_type='specific_students', allowed_students=user),
            is_active=True
        )

        # Add priority ordering using Case/When
        # Priority: 1 = Active (can take now), 2 = Upcoming, 3 = Expired
        queryset = base_queryset.annotate(
            priority=Case(
                # Active exams (can take now) - Priority 1
                When(
                    start_date_time__lte=now,
                    end_date_time__gte=now,
                    then=1
                ),
                # Upcoming exams - Priority 2
                When(
                    start_date_time__gt=now,
                    then=2
                ),
                # Expired exams - Priority 3
                When(
                    end_date_time__lt=now,
                    then=3
                ),
                default=3,
                output_field=IntegerField()
            )
        ).order_by('priority', 'start_date_time')

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user_role'] = 'Student'

        now = timezone.now()
        user = self.request.user

        # Get base queryset for stats (without annotation to avoid duplication)
        base_queryset = Exam.objects.filter(
            Q(access_type='all_students') |
            Q(access_type='specific_students', allowed_students=user),
            is_active=True
        )

        # Calculate stats
        context['available_exams'] = base_queryset.filter(
            start_date_time__lte=now,
            end_date_time__gte=now
        ).count()

        context['upcoming_exams'] = base_queryset.filter(
            start_date_time__gt=now
        ).count()

        context['total_exams'] = base_queryset.count()

        # Add exam status information for each exam in the current page
        exams_with_status = []
        for exam in context['exams']:
            exam_status = exam.get_status_for_student(user)
            attempts_made = exam.get_student_attempts(user)
            remaining_attempts = exam.get_remaining_attempts(user)
            can_attempt = exam.can_student_attempt(user)

            exams_with_status.append({
                'exam': exam,
                'status': exam_status,
                'attempts_made': attempts_made,
                'remaining_attempts': remaining_attempts,
                'can_attempt': can_attempt,
                'can_take_now': exam_status == 'available' and can_attempt,
            })

        context['exams_with_status'] = exams_with_status

        return context


class ExamCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Exam
    form_class = ExamForm
    template_name = 'exam/create_exam.html'

    def test_func(self):
        return self.request.user.is_teacher

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add student count information for better user experience
        total_students = User.objects.filter(user_type='student').count()
        context['total_students'] = total_students

        if total_students == 0:
            messages.warning(
                self.request,
                'No students are registered in the system. You may need to register students before creating an exam.'
            )

        return context

    def form_valid(self, form):
        form.instance.teacher = self.request.user
        messages.success(self.request, 'Exam created successfully! Now add questions to complete your exam.')
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse('exam:exam_detail', kwargs={'pk': self.object.pk})

    def handle_no_permission(self):
        messages.error(self.request, 'Access denied. Teachers only.')
        return redirect('exam:dashboard')


class QuestionManagementView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_teacher

    def dispatch(self, request, *args, **kwargs):
        self.exam = get_object_or_404(Exam, pk=kwargs['exam_id'], teacher=request.user)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, exam_id):
        questions = self.exam.questions.all().order_by('order')
        context = {
            'exam': self.exam,
            'questions': questions,
            'total_questions': questions.count(),
        }
        return render(request, 'exam/manage_questions.html', context)

    def post(self, request, exam_id):
        action = request.POST.get('action')

        if action == 'add_question':
            return self._add_question(request)
        elif action == 'delete_question':
            return self._delete_question(request)
        elif action == 'save_answers':
            return self._save_answer_key(request)

        return redirect('exam:manage_questions', exam_id=exam_id)

    def _add_question(self, request):
        question_text = request.POST.get('question_text', '').strip()
        marks = request.POST.get('marks', 1)
        choices = [
            request.POST.get('choice_a', '').strip(),
            request.POST.get('choice_b', '').strip(),
            request.POST.get('choice_c', '').strip(),
            request.POST.get('choice_d', '').strip(),
        ]
        correct_answer = request.POST.get('correct_answer', '').upper()

        # Validation
        if not question_text:
            messages.error(request, 'Question text is required.')
            return redirect('exam:manage_questions', exam_id=self.exam.pk)

        if not all(choices):
            messages.error(request, 'All four choices (A, B, C, D) are required.')
            return redirect('exam:manage_questions', exam_id=self.exam.pk)

        if correct_answer not in ['A', 'B', 'C', 'D']:
            messages.error(request, 'Please select a valid correct answer (A, B, C, or D).')
            return redirect('exam:manage_questions', exam_id=self.exam.pk)

        try:
            with transaction.atomic():
                # Get the next question order
                last_question = self.exam.questions.order_by('-order').first()
                next_order = (last_question.order + 1) if last_question else 1

                # Create question
                question = Question.objects.create(
                    exam=self.exam,
                    question_text=question_text,
                    marks=int(marks),
                    order=next_order
                )

                # Create choices
                choice_labels = ['A', 'B', 'C', 'D']
                created_choices = []
                for i, choice_text in enumerate(choices):
                    choice = QuestionChoice.objects.create(
                        question=question,
                        choice_text=choice_text,
                        choice_label=choice_labels[i],
                        order=i + 1
                    )
                    created_choices.append(choice)

                # Create or update answer key
                answer_key, created = AnswerKey.objects.get_or_create(
                    exam=self.exam,
                    defaults={'created_by': request.user}
                )

                # Find the correct choice and create correct answer
                correct_choice = next(choice for choice in created_choices if choice.choice_label == correct_answer)
                CorrectAnswer.objects.create(
                    answer_key=answer_key,
                    question=question,
                    correct_choice=correct_choice
                )

                messages.success(request, f'Question {next_order} added successfully!')


        except Exception as e:
            messages.error(request, f'Error adding question: {str(e)}')

        return redirect('exam:manage_questions', exam_id=self.exam.pk)

    def _delete_question(self, request):
        question_id = request.POST.get('question_id')
        try:
            question = Question.objects.get(id=question_id, exam=self.exam)
            question_order = question.order
            question.delete()

            # Reorder remaining questions
            remaining_questions = self.exam.questions.filter(order__gt=question_order).order_by('order')
            for i, q in enumerate(remaining_questions):
                q.order = question_order + i
                q.save()

            messages.success(request, 'Question deleted successfully!')
        except Question.DoesNotExist:
            messages.error(request, 'Question not found.')
        except Exception as e:
            messages.error(request, f'Error deleting question: {str(e)}')

        return redirect('exam:manage_questions', exam_id=self.exam.pk)

    def _save_answer_key(self, request):
        try:
            changes_made = False
            with transaction.atomic():
                answer_key, created = AnswerKey.objects.get_or_create(
                    exam=self.exam,
                    defaults={'created_by': request.user}
                )

                # Update all correct answers
                for question in self.exam.questions.all():
                    correct_choice_id = request.POST.get(f'question_{question.id}_answer')

                    if correct_choice_id:
                        try:
                            correct_choice = QuestionChoice.objects.get(
                                id=correct_choice_id,
                                question=question
                            )

                            # Check if this is actually a change
                            existing_answer = CorrectAnswer.objects.filter(
                                answer_key=answer_key,
                                question=question
                            ).first()

                            if not existing_answer or existing_answer.correct_choice_id != int(correct_choice_id):
                                changes_made = True

                            # Update or create correct answer
                            CorrectAnswer.objects.update_or_create(
                                answer_key=answer_key,
                                question=question,
                                defaults={'correct_choice': correct_choice}
                            )
                        except QuestionChoice.DoesNotExist:
                            continue

                if changes_made:
                    messages.success(request, 'Answer key updated successfully!')
                else:
                    messages.info(request, 'No changes were made to the answer key.')

        except Exception as e:
            messages.error(request, f'Error saving answer key: {str(e)}')

        return redirect('exam:manage_questions', exam_id=self.exam.pk)


class ExamDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Exam
    template_name = 'exam/exam_detail.html'
    context_object_name = 'exam'

    def test_func(self):
        exam = self.get_object()
        return self.request.user.is_teacher and exam.teacher == self.request.user

    def handle_no_permission(self):
        messages.error(self.request, 'Access denied. You can only view exams you created.')
        return redirect('exam:teacher_dashboard')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        exam = self.object

        # Get all students who can access this exam
        if exam.access_type == 'all_students':
            eligible_students = User.objects.filter(user_type='student')
        else:
            eligible_students = exam.allowed_students.all()

        # Get submission data for each student
        student_data = []
        for student in eligible_students:
            try:
                submission = ExamSubmission.objects.get(exam=exam, student=student)
                if submission.is_completed:
                    status = 'Completed'
                    score_display = f"{submission.score}/{submission.total_marks} ({submission.percentage:.1f}%)"
                    submitted_at = submission.submitted_at
                else:
                    status = 'In Progress'
                    score_display = 'In Progress'
                    submitted_at = None
            except ExamSubmission.DoesNotExist:
                status = 'Not Started'
                score_display = 'Did not take yet'
                submitted_at = None

            student_data.append({
                'student': student,
                'status': status,
                'score_display': score_display,
                'submitted_at': submitted_at,
            })

        # Sort by status (completed first, then by name)
        student_data.sort(key=lambda x: (x['status'] != 'Completed', x['student'].get_full_name()))

        # Calculate statistics
        total_students = len(student_data)
        completed_submissions = len([s for s in student_data if s['status'] == 'Completed'])
        in_progress = len([s for s in student_data if s['status'] == 'In Progress'])
        not_started = len([s for s in student_data if s['status'] == 'Not Started'])

        # Calculate average score for completed submissions
        completed_submissions_objects = ExamSubmission.objects.filter(
            exam=exam,
            is_completed=True
        )
        from django.db import models
        average_score = completed_submissions_objects.aggregate(
            avg_score=models.Avg('percentage')
        )['avg_score'] or 0

        context.update({
            'student_data': student_data,
            'total_students': total_students,
            'completed_count': completed_submissions,
            'in_progress_count': in_progress,
            'not_started_count': not_started,
            'average_score': round(average_score, 1),
            'total_questions': exam.questions.count(),
            'can_edit': not exam.is_expired(),
        })

        return context


class ExamUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Exam
    form_class = ExamForm
    template_name = 'exam/edit_exam.html'

    def test_func(self):
        exam = self.get_object()
        return (self.request.user.is_teacher and
                exam.teacher == self.request.user and
                not exam.is_expired())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add student count information for better user experience
        total_students = User.objects.filter(user_type='student').count()
        context['total_students'] = total_students

        if total_students == 0:
            messages.warning(
                self.request,
                'No students are registered in the system. You may need to register students before updating this exam.'
            )

        return context

    def handle_no_permission(self):
        exam = self.get_object()
        if exam.is_expired():
            messages.error(self.request, 'Cannot edit exam after the deadline has passed.')
        else:
            messages.error(self.request, 'Access denied. You can only edit exams you created.')
        return redirect('exam:exam_detail', pk=exam.pk)

    def form_valid(self, form):
        messages.success(self.request, 'Exam updated successfully!')
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse('exam:exam_detail', kwargs={'pk': self.object.pk})


class StudentExamView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Exam
    template_name = 'exam/student_exam.html'
    context_object_name = 'exam'

    def test_func(self):
        return self.request.user.is_student

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        exam = self.get_object()
        student = self.request.user

        exam_status = exam.get_status_for_student(student)
        context['exam_status'] = exam_status

        # Get attempt information
        context['attempts_made'] = exam.get_student_attempts(student)
        context['remaining_attempts'] = exam.get_remaining_attempts(student)
        context['max_attempts'] = exam.max_attempts

        # Check for ongoing submission
        ongoing_submission = exam.submissions.filter(
            student=student,
            is_completed=False
        ).first()

        if ongoing_submission and not ongoing_submission.is_time_up():
            context['ongoing_submission'] = ongoing_submission
            context['time_remaining'] = ongoing_submission.get_time_remaining()

        # Get completed submissions for this student
        completed_submissions = exam.submissions.filter(
            student=student,
            is_completed=True
        ).order_by('-submitted_at')
        context['completed_submissions'] = completed_submissions

        return context

    def handle_no_permission(self):
        messages.error(self.request, 'Access denied. Students only.')
        return redirect('exam:dashboard')


class StartExamView(LoginRequiredMixin, UserPassesTestMixin, View):
    """View to start a new exam attempt"""

    def test_func(self):
        return self.request.user.is_student

    def post(self, request, pk):
        exam = get_object_or_404(Exam, pk=pk)
        student = request.user

        # Create new submission
        try:
            with transaction.atomic():
                # Generate randomized question order
                questions = list(exam.questions.values_list('id', flat=True))
                random.shuffle(questions)

                submission = ExamSubmission.objects.create(
                    exam=exam,
                    student=student,
                    total_marks=exam.total_marks,
                    question_order=questions
                )

                messages.success(request, f'Exam started! You have {exam.duration_minutes} minutes to complete.')
                return redirect('exam:take_exam', submission_id=submission.id)

        except Exception as e:
            messages.error(request, 'Failed to start exam. Please try again.')
            return redirect('exam:student_exam', pk=pk)

    def handle_no_permission(self):
        messages.error(self.request, 'Access denied. Students only.')
        return redirect('exam:dashboard')


class TakeExamView(LoginRequiredMixin, UserPassesTestMixin, View):
    """View for student to take the exam"""

    def test_func(self):
        return self.request.user.is_student

    def get_submission(self, submission_id):
        """Get submission and verify it belongs to current user"""
        return get_object_or_404(
            ExamSubmission,
            id=submission_id,
            student=self.request.user,
            is_completed=False
        )

    def get(self, request, submission_id):
        submission = self.get_submission(submission_id)

        # Check if time is up
        if submission.is_time_up():
            return self.auto_submit_exam(submission)

        # Get questions in randomized order
        question_ids = submission.question_order
        questions = []

        for q_id in question_ids:
            try:
                question = Question.objects.get(id=q_id, exam=submission.exam)
                questions.append(question)
            except Question.DoesNotExist:
                continue

        # Get existing answers
        existing_answers = {}
        for answer in submission.answers.all():
            existing_answers[answer.question.id] = answer.selected_choice.id if answer.selected_choice else None

        context = {
            'submission': submission,
            'exam': submission.exam,
            'questions': questions,
            'existing_answers': existing_answers,
            'time_remaining': submission.get_time_remaining(),
            'total_questions': len(questions),
        }

        return render(request, 'exam/take_exam.html', context)

    def post(self, request, submission_id):
        submission = self.get_submission(submission_id)

        # Check if time is up
        if submission.is_time_up():
            return self.auto_submit_exam(submission)

        action = request.POST.get('action')

        if action == 'save_answer':
            return self.save_answer(request, submission)
        elif action == 'submit_exam':
            return self.submit_exam(request, submission)
        elif action == 'get_time':
            return JsonResponse({'time_remaining': submission.get_time_remaining()})

        return redirect('exam:take_exam', submission_id=submission_id)

    def save_answer(self, request, submission):
        """Save student's answer to a question"""
        question_id = request.POST.get('question_id')
        choice_id = request.POST.get('choice_id')

        try:
            question = Question.objects.get(id=question_id, exam=submission.exam)
            choice = QuestionChoice.objects.get(id=choice_id, question=question) if choice_id else None

            # Update or create answer
            answer, created = StudentAnswer.objects.update_or_create(
                submission=submission,
                question=question,
                defaults={'selected_choice': choice}
            )

            return JsonResponse({'success': True, 'message': 'Answer saved'})

        except (Question.DoesNotExist, QuestionChoice.DoesNotExist):
            return JsonResponse({'success': False, 'message': 'Invalid question or choice'})

    def submit_exam(self, request, submission):
        """Submit the exam"""
        print(f"DEBUG: submit_exam called for submission {submission.id}")  # Debug line
        try:
            with transaction.atomic():
                submission.submitted_at = timezone.now()
                submission.is_completed = True
                submission.time_taken = submission.submitted_at - submission.started_at

                # Calculate score and total marks
                score = 0
                total_marks = submission.exam.questions.aggregate(
                    total=Sum('marks')
                )['total'] or 0

                for answer in submission.answers.all():
                    if answer.is_correct():
                        score += answer.question.marks

                submission.score = score
                submission.total_marks = total_marks
                submission.calculate_percentage()  # This will calculate percentage
                submission.save()

                print(f"DEBUG: Exam submitted successfully. Score: {score}/{submission.total_marks}")  # Debug line
                messages.success(request, f'Exam submitted successfully! Your score: {score}/{submission.total_marks}')
                return redirect('exam:exam_result', submission_id=submission.id)

        except Exception as e:
            print(f"DEBUG: Error submitting exam: {e}")  # Debug line
            messages.error(request, 'Failed to submit exam. Please try again.')
            return redirect('exam:take_exam', submission_id=submission.id)

    def auto_submit_exam(self, submission):
        """Auto-submit exam when time is up"""
        if not submission.is_completed:
            try:
                with transaction.atomic():
                    submission.submitted_at = timezone.now()
                    submission.is_completed = True
                    submission.auto_submitted = True
                    submission.time_taken = timezone.timedelta(minutes=submission.exam.duration_minutes)

                    # Calculate score and total marks
                    score = 0
                    total_marks = submission.exam.questions.aggregate(
                        total=Sum('marks')
                    )['total'] or 0

                    for answer in submission.answers.all():
                        if answer.is_correct():
                            score += answer.question.marks

                    submission.score = score
                    submission.total_marks = total_marks
                    submission.calculate_percentage()  # This will calculate percentage
                    submission.save()

                    messages.warning(self.request, 'Time is up! Your exam has been automatically submitted.')
            except:
                pass

        return redirect('exam:exam_result', submission_id=submission.id)

    def handle_no_permission(self):
        messages.error(self.request, 'Access denied. Students only.')
        return redirect('exam:dashboard')


class ExamResultView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """View to show exam results"""
    model = ExamSubmission
    template_name = 'exam/exam_result.html'
    context_object_name = 'submission'
    pk_url_kwarg = 'submission_id'

    def test_func(self):
        submission = self.get_object()
        return (self.request.user.is_student and
                submission.student == self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        submission = self.get_object()

        # Get all answers with correct/incorrect status
        answers_data = []
        for answer in submission.answers.all():
            try:
                correct_answer = CorrectAnswer.objects.get(
                    answer_key__exam=submission.exam,
                    question=answer.question
                )
                is_correct = answer.selected_choice == correct_answer.correct_choice
                points_earned = answer.question.marks if is_correct else 0
            except CorrectAnswer.DoesNotExist:
                is_correct = False
                points_earned = 0
                correct_answer = None

            answers_data.append({
                'question': answer.question,
                'selected_choice': answer.selected_choice,
                'correct_choice': correct_answer.correct_choice if correct_answer else None,
                'is_correct': is_correct,
                'points_earned': points_earned,
                'explanation': correct_answer.explanation if correct_answer else '',
            })

        context['answers_data'] = answers_data
        context['percentage'] = submission.percentage

        return context

    def handle_no_permission(self):
        messages.error(self.request, 'Access denied.')
        return redirect('exam:dashboard')
