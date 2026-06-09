"""
Django admin customization.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from core.models import Desing, Message, Model, Template, User


@admin.register(Desing)
class DesingAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'name']
    search_fields = ['created_at', 'name']
    list_filter = ['created_at']
    ordering = ['created_at', 'name']
    list_per_page = 10


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'name']
    search_fields = ['created_at', 'name']
    list_filter = ['created_at']
    ordering = ['created_at', 'name']
    list_per_page = 10


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('status', 'sent_at')
    search_fields = ('status', 'sent_at')
    list_filter = ('status', 'sent_at')
    ordering = ('status', 'sent_at')
    list_per_page = 10


@admin.register(Model)
class ModelAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'name']
    search_fields = ['created_at', 'name']
    list_filter = ['created_at']
    ordering = ['created_at', 'name']
    list_per_page = 10


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Define the admin pages for users."""

    ordering = ['id']
    list_display = ['email', 'name', 'user_type', 'is_active', 'created_at', "get_profile_photo_preview"]
    search_fields = ['email', 'name', 'created_at']
    list_filter = ['is_active', 'is_staff', 'user_type']

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal Info'), {'fields': ('name', 'user_type', 'profile_photo')}),
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

    readonly_fields = ['last_login', 'created_at', 'get_profile_photo_preview']

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
                    "profile_photo",
                    "get_profile_photo_preview",
                ),
            },
        ),
    )

    def get_profile_photo_preview(self, obj):
        if obj.profile_photo and obj.profile_photo.url:
            return format_html(
                '<img src="{}" style="height: 80px; width: 80px; object-fit: cover; border-radius: 8px;" />',
                obj.profile_photo.url
            )
        return "Sem imagem"

    get_profile_photo_preview.short_description = "Pré-visualização da foto"
