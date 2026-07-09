from rest_framework import serializers
from rest_framework.serializers import ModelSerializer, SlugRelatedField

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
                  'user_type']
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
        password = validated_data.pop('password', None)
        instance = super().update(instance, validated_data)
        if password:
            instance.set_password(password)
            instance.save()
        return instance


class UserRegistrationSerializer(ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['id', 'email', 'name', 'password', 'user_type']

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)
