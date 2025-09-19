from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.contrib.auth.base_user import BaseUserManager
from django.db import models
from django.utils import timezone


class CustomUserManager(BaseUserManager):
    """
    Custom user manager for CustomUser model.
    Provides methods to create regular users, superusers, teachers, and students.
    """
    
    def create_user(self, email, first_name, last_name, password=None, **extra_fields):
        """
        Create and return a regular user with an email and password.
        """
        if not email:
            raise ValueError('The Email field must be set')
        
        email = self.normalize_email(email)
        user = self.model(
            email=email,
            first_name=first_name,
            last_name=last_name,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, first_name, last_name, password=None, **extra_fields):
        """
        Create and return a superuser with admin privileges.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('user_type', CustomUser.ADMIN)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(email, first_name, last_name, password, **extra_fields)
    
    def create_teacher(self, email, first_name, last_name, password=None, **extra_fields):
        """
        Create and return a teacher user with appropriate permissions.
        """
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('user_type', CustomUser.TEACHER)
        
        return self.create_user(email, first_name, last_name, password, **extra_fields)
    
    def create_student(self, email, first_name, last_name, password=None, **extra_fields):
        """
        Create and return a student user with basic permissions.
        """
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('user_type', CustomUser.STUDENT)
        
        return self.create_user(email, first_name, last_name, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model that uses email as the unique identifier.
    Supports three user types: Admin, Teacher, and Student.
    """
    
    # User type choices
    ADMIN = 'admin'
    TEACHER = 'teacher'
    STUDENT = 'student'
    
    USER_TYPE_CHOICES = [
        (ADMIN, 'Admin'),
        (TEACHER, 'Teacher'),
        (STUDENT, 'Student'),
    ]
    
    # Basic user information
    email = models.EmailField(
        unique=True,
        verbose_name='Email Address',
        help_text='Required. Enter a valid email address.'
    )
    first_name = models.CharField(
        max_length=30,
        verbose_name='First Name',
        help_text='Required. 30 characters or fewer.'
    )
    last_name = models.CharField(
        max_length=30,
        verbose_name='Last Name',
        help_text='Required. 30 characters or fewer.'
    )
    
    # User type and permissions
    user_type = models.CharField(
        max_length=10,
        choices=USER_TYPE_CHOICES,
        default=STUDENT,
        verbose_name='User Type',
        help_text='Designates the type of user (Admin, Teacher, or Student).'
    )
    
    # Status fields
    is_active = models.BooleanField(
        default=True,
        verbose_name='Active Status',
        help_text='Designates whether this user should be treated as active.'
    )
    is_staff = models.BooleanField(
        default=False,
        verbose_name='Staff Status',
        help_text='Designates whether the user can log into the admin site.'
    )
    
    # Timestamps
    date_joined = models.DateTimeField(
        default=timezone.now,
        verbose_name='Date Joined'
    )
    last_login = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Last Login'
    )
    
    # Set email as the username field
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']
    
    # Use custom manager
    objects = CustomUserManager()
    
    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['date_joined']
    
    def __str__(self):
        """Return string representation of the user."""
        return f"{self.get_full_name()} ({self.email})"
    
    def get_full_name(self):
        """Return the user's full name."""
        return f"{self.first_name} {self.last_name}".strip()
    
    def get_short_name(self):
        """Return the user's first name."""
        return self.first_name
    
    @property
    def is_teacher(self):
        """Check if user is a teacher."""
        return self.user_type == self.TEACHER
    
    @property
    def is_student(self):
        """Check if user is a student."""
        return self.user_type == self.STUDENT
    
    def has_teacher_permissions(self):
        """Check if user has teacher-level permissions or higher."""
        return self.user_type in [self.TEACHER, self.ADMIN] or self.is_superuser
    
    def has_admin_permissions(self):
        """Check if user has admin-level permissions."""
        return self.user_type == self.ADMIN or self.is_superuser
