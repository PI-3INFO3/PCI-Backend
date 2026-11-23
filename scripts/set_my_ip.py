#!/usr/bin/env python3

import os
import socket


# Função para obter o IP do computador
def get_current_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        print(f'Erro ao obter o IP: {e}')
        return None


# Função para atualizar o arquivo .env com o novo IP
def _write_current_ip(ip):
    if not os.path.isfile('.env'):
        with open('.env', 'w', encoding='utf-8') as new_file:
            new_file.write(f'MY_IP={ip}\n')
        return

    with open('.env', 'r', encoding='utf-8') as file:
        lines = file.readlines()

    with open('.env', 'w', encoding='utf-8') as file:
        for line in lines:
            if not line.startswith('MY_IP='):
                file.write(line)
        file.write(f'MY_IP={ip}\n')


def update_env_file(ip):
    try:
        _write_current_ip(ip)
    except OSError as exc:
        print(f'Erro ao atualizar o arquivo .env: {exc}')
    else:
        print(f'IP atualizado no arquivo .env: MY_IP={ip}')


# Função principal
def main():
    ip = get_current_ip()
    if ip:
        update_env_file(ip)


if __name__ == '__main__':
    main()
