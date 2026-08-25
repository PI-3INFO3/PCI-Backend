from rest_framework import serializers
from rest_framework.serializers import ModelSerializer, SlugRelatedField
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from core.models import User
from uploader.models import Image
from uploader.serializers import ImageSerializer


class UserSerializer(ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)

    class Meta:
        model = User
        fields = ['id',
                  'email',
                  'name',
                  'is_active',
                  'is_staff',
                  'is_superuser',
                  'last_login',
                  'groups',
                  'profile_photo',
                  'profile_photo_attachment_key',
                  'password',
                  'theme',
                  'user_type',
                  'email_verified']
        read_only_fields = ['email_verified']
        depth = 1

    profile_photo_attachment_key = SlugRelatedField(
        source='profile_photo',
        queryset=Image.objects.all(),
        slug_field='attachment_key',
        required=False,
        write_only=True,
    )
    profile_photo = ImageSerializer(
        required=False,
        read_only=True
    )

    def update(self, instance, validated_data):
        validated_data.pop('password', None)
        return super().update(instance, validated_data)


class UserRegistrationSerializer(ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['id', 'email', 'name', 'password', 'user_type']

    def validate_email(self, value):
        existing = User.objects.filter(email=value).first()
        if existing:
            if existing.email_verified:
                raise serializers.ValidationError('Este e-mail já está cadastrado.')
            existing.delete()
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, min_length=8)

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Senha atual incorreta.')
        return value

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    codigo = serializers.CharField(max_length=6)


class ResendCodeSerializer(serializers.Serializer):
    email = serializers.EmailField()


class EmailVerifiedTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login padrão, mas recusa gerar token se o e-mail não estiver verificado."""

    def validate(self, attrs):
        data = super().validate(attrs)
        if not self.user.email_verified:
            raise serializers.ValidationError(
                {'detail': 'Você precisa verificar seu e-mail antes de fazer login.'},
                code='email_not_verified',
            )
        return data
