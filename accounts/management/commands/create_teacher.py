from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from accounts.models import CustomUser
import getpass


class Command(BaseCommand):
    help = 'Create a teacher user interactively'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            help='The email address of the teacher (optional, will prompt if not provided)',
        )
        parser.add_argument(
            '--first-name',
            type=str,
            help='The first name of the teacher (optional, will prompt if not provided)',
        )
        parser.add_argument(
            '--last-name',
            type=str,
            help='The last name of the teacher (optional, will prompt if not provided)',
        )

    def handle(self, *args, **options):
        # Get email
        email = options.get('email')
        if not email:
            email = self.get_email()
        else:
            # Validate provided email
            try:
                validate_email(email)
            except ValidationError:
                raise CommandError('Invalid email address format.')

        # Check if user already exists
        if CustomUser.objects.filter(email=email).exists():
            raise CommandError(f'User with email "{email}" already exists.')

        # Get first name
        first_name = options.get('first_name')
        if not first_name:
            first_name = self.get_input('First name: ')

        # Get last name
        last_name = options.get('last_name')
        if not last_name:
            last_name = self.get_input('Last name: ')

        # Get password
        password = self.get_password()

        try:
            teacher = CustomUser.objects.create_teacher(
                email=email,
                first_name=first_name,
                last_name=last_name,
                password=password
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully created teacher: {teacher.get_full_name()} ({teacher.email})'
                )
            )
        except Exception as e:
            raise CommandError(f'Error creating teacher: {e}')

    def get_email(self):
        """Prompt for email with validation."""
        while True:
            email = input('Email address: ').strip()
            if not email:
                self.stdout.write(self.style.ERROR('Email cannot be empty.'))
                continue
            
            try:
                validate_email(email)
            except ValidationError:
                self.stdout.write(self.style.ERROR('Enter a valid email address.'))
                continue
            
            # Check if email already exists
            if CustomUser.objects.filter(email=email).exists():
                self.stdout.write(self.style.ERROR(f'User with email "{email}" already exists.'))
                continue
            
            return email

    def get_input(self, prompt):
        """Get input with validation for required fields."""
        while True:
            value = input(prompt).strip()
            if not value:
                self.stdout.write(self.style.ERROR('This field cannot be empty.'))
                continue
            return value

    def get_password(self):
        """Prompt for password with confirmation."""
        while True:
            password = getpass.getpass('Password: ')
            if not password:
                self.stdout.write(self.style.ERROR('Password cannot be empty.'))
                continue
            
            password_confirm = getpass.getpass('Password (again): ')
            if password != password_confirm:
                self.stdout.write(self.style.ERROR('Passwords do not match.'))
                continue
            
            return password