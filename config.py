"""Configuracao comum (pode ser sobrescrita por variaveis de ambiente ou argumentos)."""
import os
import socket
import threading
import time

NS_HOST = os.environ.get("NS_HOST", "localhost")
NS_PORT = int(os.environ.get("NS_PORT", "5678"))

CALC_NAME = os.environ.get("CALC_NAME", "calculadora")
KV_NAME = os.environ.get("KV_NAME", "armazenamento")

CALC_PORT = int(os.environ.get("CALC_PORT", "50051"))
KV_PORT = int(os.environ.get("KV_PORT", "50052"))

RPC_TIMEOUT = float(os.environ.get("RPC_TIMEOUT", "3"))

HOSTNAME = socket.gethostname()


def ip_local(destino=NS_HOST, porta=NS_PORT):
	try:
		with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
			s.connect((socket.gethostbyname(destino), porta))
			ip = s.getsockname()[0]
			if not ip.startswith("127.") or destino in ("localhost", "127.0.0.1"):
				return ip
	except OSError:
		pass
	try:
		return socket.gethostbyname(HOSTNAME)
	except OSError:
		return "127.0.0.1"


_log_lock = threading.Lock()


def log(*args):
	linha = " ".join([time.strftime("[%H:%M:%S]"), *map(str, args)])
	with _log_lock:
		print(linha, flush=True)
