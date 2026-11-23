"""Definições vetoriais compartilhadas, sem converter para PNG."""

import hashlib

from core.models import Symbol

MIN_SYMBOL_PATH_LENGTH = 5
MAX_SYMBOL_PATH_LENGTH = 4000

# viewBox comum 0 0 100 100; paths suportados pelo fabric.Path.
DEFAULT_SYMBOLS = {
    'balao': (
        'Balão de fala',
        'M 12 10 H 88 Q 96 10 96 20 V 66 Q 96 76 86 76 H 43 L 18 96 L 24 76 H 12 Q 4 76 4 66 V 20 Q 4 10 12 10 Z',
    ),
    'nuvem': (
        'Nuvem',
        'M 24 75 C 6 75 3 57 15 48 C 14 25 37 19 49 32 C 62 16 88 29 85 48 C 107 56 98 78 79 78 H 27 Z',
    ),
    'coracao': (
        'Coração',
        'M 50 89 C 40 78 5 53 5 31 C 5 6 36 2 50 25 C 64 2 95 6 95 31 C 95 53 60 78 50 89 Z',
    ),
    'raio': ('Raio', 'M 56 3 L 20 54 H 44 L 36 97 L 84 41 H 58 Z'),
    'seta': ('Seta', 'M 5 36 H 61 V 17 L 96 50 L 61 83 V 64 H 5 Z'),
    'losango': ('Losango', 'M 50 3 L 97 50 L 50 97 L 3 50 Z'),
    'hexagono': ('Hexágono', 'M 25 7 H 75 L 98 50 L 75 93 H 25 L 2 50 Z'),
}


def symbol_hash(path_data):
    return hashlib.sha256(path_data.encode('utf-8')).hexdigest()


def get_or_create_symbol(key):
    name, path_data = DEFAULT_SYMBOLS[key]
    hash_value = symbol_hash(path_data)
    symbol, _ = Symbol.objects.get_or_create(
        content_hash=hash_value,
        defaults={'key': key, 'name': name, 'path_data': path_data},
    )
    return symbol


def get_or_create_path_symbol(name, path_data):
    """Reutiliza símbolo idêntico de qualquer apresentação/usuário."""

    path_data = path_data.strip()
    hash_value = symbol_hash(path_data)
    symbol, _ = Symbol.objects.get_or_create(
        content_hash=hash_value,
        defaults={
            'key': f'simbolo-{hash_value[:24]}',
            'name': (name or 'Símbolo importado')[:120],
            'path_data': path_data,
        },
    )
    return symbol
