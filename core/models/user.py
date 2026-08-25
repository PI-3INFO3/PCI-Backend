"""
Database models.
"""

import random

from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.core.mail import send_mail
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from uploader.models import Image


class UserManager(BaseUserManager):
    """Manager for users."""

    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        """Create, save and return a new user."""
        if not email:
            raise ValueError('Users must have an email address.')

        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(self, email, password):
        """Create, save and return a new superuser."""
        user = self.create_user(email, password)
        user.is_staff = True
        user.is_superuser = True
        user.email_verified = True  # superusuário não precisa verificar
        user.save(using=self._db)

        return user


class User(AbstractBaseUser, PermissionsMixin):
    """User model in the system."""

    class ThemeChoices(models.TextChoices):
        LIGHT = 'Claro', 'Claro'
        DARK = 'Escuro', 'Escuro'

    class UserType(models.TextChoices):
        PERSONAL = 'personal', 'Pessoal'
        EDUCATIONAL = 'educational', 'Educacional'
        PROFESSIONAL = 'professional', 'Professional'

    email = models.EmailField(
        max_length=255, unique=True, verbose_name=_('email'), help_text=_('Email'))
    name = models.CharField(
        max_length=255, blank=True, null=True, verbose_name=_('name'), help_text=_('Username'))
    user_type = models.CharField(
        max_length=20,
        choices=UserType.choices,
        default=UserType.PERSONAL
    )
    profile_photo = models.ForeignKey(
        Image,
        related_name='+',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
    )
    theme = models.CharField(
        max_length=10,
        choices=ThemeChoices.choices,
        default=ThemeChoices.LIGHT,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    is_active = models.BooleanField(
        default=True, verbose_name=_('Usuário está ativo'), help_text=_('Indica que este usuário está ativo.')
    )
    is_staff = models.BooleanField(
        default=False,
        verbose_name=_('Usuário é da equipe'),
        help_text=_('Indica que este usuário pode acessar o Admin.'),
    )

    # Campos de verificação de e-mail
    email_verified = models.BooleanField(
        default=False,
        verbose_name=_('E-mail verificado'),
        help_text=_('Indica se o usuário confirmou o e-mail cadastrado.'),
    )
    verification_code = models.CharField(max_length=6, blank=True, null=True)
    verification_code_created_at = models.DateTimeField(blank=True, null=True)
    verification_attempts = models.PositiveSmallIntegerField(default=0)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        """Meta options for the model."""

        verbose_name = 'Usuário'
        verbose_name_plural = 'Usuários'

    def generate_verification_code(self):
        """Gera um novo código de 6 dígitos e reseta as tentativas."""
        self.verification_code = str(random.randint(100000, 999999))
        self.verification_code_created_at = timezone.now()
        self.verification_attempts = 0
        self.save(update_fields=[
            'verification_code',
            'verification_code_created_at',
            'verification_attempts',
        ])
        return self.verification_code

    def is_code_expired(self):
        """Verifica se o código de verificação atual já expirou (10 minutos)."""
        if not self.verification_code_created_at:
            return True
        return timezone.now() > self.verification_code_created_at + timezone.timedelta(minutes=10)

    def send_verification_email(self):
        """Gera um novo código e envia por e-mail para o usuário."""

        code = self.generate_verification_code()
        send_mail(
            subject='Confirme seu e-mail',
            message=f'Seu código de verificação é: {code}\nEle expira em 10 minutos.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[self.email],
            fail_silently=False,
        )
