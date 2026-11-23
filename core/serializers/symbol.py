import re

from rest_framework import serializers

from core.models import Symbol
from core.services.symbols import (
    MAX_SYMBOL_PATH_LENGTH,
    MIN_SYMBOL_PATH_LENGTH,
    symbol_hash,
)


class SymbolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Symbol
        fields = ['id', 'key', 'name', 'path_data', 'created_at']
        read_only_fields = ['id', 'key', 'created_at']

    def validate_path_data(self, value):
        # Aceita exclusivamente comandos SVG path, não atributos ou markup.
        if not MIN_SYMBOL_PATH_LENGTH <= len(value) <= MAX_SYMBOL_PATH_LENGTH or not re.fullmatch(
            r'[MmLlHhVvCcSsQqTtAaZz0-9\s,\.\-+eE]+', value
        ):
            raise serializers.ValidationError('Informe somente geometria de um caminho SVG válido.')
        return value.strip()

    def create(self, validated_data):
        digest = symbol_hash(validated_data['path_data'])
        symbol, _ = Symbol.objects.get_or_create(
            content_hash=digest,
            defaults={
                'key': f'simbolo-{digest[:24]}',
                'name': validated_data['name'],
                'path_data': validated_data['path_data'],
            },
        )
        return symbol
