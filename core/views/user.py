from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import CreateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import User
from core.serializers import (
    ChangePasswordSerializer,
    ResendCodeSerializer,
    UserRegistrationSerializer,
    UserSerializer,
    VerifyEmailSerializer,
)

MAX_VERIFICATION_ATTEMPTS = 5


class UserViewSet(ModelViewSet):
    queryset = User.objects.all().order_by('id')
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Dados do usuário autenticado",
        description="Retorna ou atualiza os dados do usuário autenticado.",
        responses={200: UserSerializer, 401: None},
    )
    @action(detail=False, methods=['get', 'patch', 'put'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """Retorna ou atualiza os dados do usuário autenticado."""
        user = request.user

        if request.method == 'GET':
            serializer = UserSerializer(user)
            return Response(serializer.data, status=status.HTTP_200_OK)

        partial = request.method == 'PATCH'
        serializer = UserSerializer(user, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Alterar senha",
        description="Altera a senha do usuário autenticado, exigindo a senha atual.",
        request=ChangePasswordSerializer,
        responses={200: None, 400: None},
    )
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        """Altera a senha do usuário autenticado, após validar a senha atual."""
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'detail': 'Senha alterada com sucesso.'}, status=status.HTTP_200_OK)


class UserRegistrationView(CreateAPIView):
    """Endpoint para registro de novos usuários. Não realiza login automático."""

    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            print("ERROS DE VALIDAÇÃO:", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def perform_create(self, serializer):
        user = serializer.save()
        user.send_verification_email()


class VerifyEmailView(APIView):
    """Confirma o código de verificação e retorna os tokens de acesso."""

    permission_classes = [AllowAny]

    @extend_schema(request=VerifyEmailSerializer, responses={200: None, 400: None, 404: None})
    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        codigo = serializer.validated_data['codigo']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'detail': 'Usuário não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        if user.email_verified:
            return Response({'detail': 'E-mail já verificado.'}, status=status.HTTP_400_BAD_REQUEST)

        if user.verification_attempts >= MAX_VERIFICATION_ATTEMPTS:
            return Response(
                {'detail': 'Muitas tentativas. Solicite um novo código.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if user.is_code_expired():
            return Response({'detail': 'Código expirado. Solicite um novo.'}, status=status.HTTP_400_BAD_REQUEST)

        if user.verification_code != codigo:
            user.verification_attempts += 1
            user.save(update_fields=['verification_attempts'])
            return Response({'detail': 'Código inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        user.email_verified = True
        user.verification_code = None
        user.save(update_fields=['email_verified', 'verification_code'])

        refresh = RefreshToken.for_user(user)
        return Response({
            'detail': 'E-mail verificado com sucesso!',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_200_OK)


class ResendVerificationCodeView(APIView):
    """Reenvia um novo código de verificação por e-mail."""

    permission_classes = [AllowAny]

    @extend_schema(request=ResendCodeSerializer, responses={200: None, 400: None, 404: None})
    def post(self, request):
        serializer = ResendCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'detail': 'Usuário não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        if user.email_verified:
            return Response({'detail': 'E-mail já verificado.'}, status=status.HTTP_400_BAD_REQUEST)

        user.send_verification_email()
        return Response({'detail': 'Novo código enviado.'}, status=status.HTTP_200_OK)
