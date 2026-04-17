"""
Django admin customization.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from core.models import Message, User


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('status', 'sent_at')
    search_fields = ('status', 'sent_at')
    list_filter = ('status', 'sent_at')
    ordering = ('status', 'sent_at')
    list_per_page = 10


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Define the admin pages for users."""

    ordering = ['id']
    list_display = ['email', 'name', 'user_type', 'is_active', 'created_at']
    search_fields = ['email', 'name', 'created_at']
    list_filter = ['is_active', 'is_staff', 'user_type']
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal Info'), {'fields': ('name', 'user_type')}),
        (
            _('Permissions'),
            {
                'fields': (
                    'is_active',
                    'is_staff',
                    'is_superuser',
                )
            },
        ),
        (_('Important dates'), {'fields': ('last_login', 'created_at')}),
        (_('Groups'), {'fields': ('groups',)}),
        (_('User Permissions'), {'fields': ('user_permissions',)}),
    )
    readonly_fields = ['last_login', 'created_at']
    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': (
                    'email',
                    'password1',
                    'password2',
                    'name',
                    'user_type',
                    'is_active',
                    'is_staff',
                    'is_superuser',
                ),
            },
        ),
    )
