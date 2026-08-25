from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import User

UNVERIFIED_ACCOUNT_EXPIRY_HOURS = 24


class Command(BaseCommand):
    help = 'Remove contas não verificadas criadas há mais de 24 horas.'

    def handle(self, *args, **options):
        limite = timezone.now() - timedelta(hours=UNVERIFIED_ACCOUNT_EXPIRY_HOURS)
        queryset = User.objects.filter(email_verified=False, created_at__lt=limite)
        total = queryset.count()
        queryset.delete()
        self.stdout.write(self.style.SUCCESS(f'{total} conta(s) não verificada(s) removida(s).'))
