"""Servico de Nomes em gRPC: bind, lookup, unbind, rebind (e list).

Uso:  python3 naming_server.py [--port 5678] [--db nomes.json]
"""
import argparse
import json
import os
import signal
import threading
import time
from concurrent import futures

import grpc

import config
import naming_pb2
import naming_pb2_grpc
from config import log


class NamingService(naming_pb2_grpc.NamingServiceServicer):
	def __init__(self, db_path=None):
		self.db_path = db_path
		self.lock = threading.Lock()
		self.reg = {}
		if db_path and os.path.exists(db_path):
			with open(db_path) as f:
				self.reg = json.load(f)
			log(f"{len(self.reg)} registro(s) carregado(s) de {db_path}")

	def _salvar(self):
		if self.db_path:
			tmp = self.db_path + ".tmp"
			with open(tmp, "w") as f:
				json.dump(self.reg, f, indent=1)
			os.replace(tmp, self.db_path)

	@staticmethod
	def _valida(request):
		if not request.name:
			return "nome vazio"
		if not request.address.host or not 0 < request.address.port < 65536:
			return "endereco invalido"
		return None

	def Bind(self, request, context):
		erro = self._valida(request)
		if erro:
			return self._status(False, erro, "BIND", request, context)
		with self.lock:
			if request.name in self.reg:
				r = self.reg[request.name]
				return self._status(False, f"nome '{request.name}' ja registrado em {r['host']}:{r['port']} (use rebind)", "BIND", request, context)
			now = time.time()
			self.reg[request.name] = {"host": request.address.host, "port": request.address.port, "registered_at": now, "updated_at": now}
			self._salvar()
		return self._status(True, f"'{request.name}' -> {request.address.host}:{request.address.port}", "BIND", request, context)

	def Rebind(self, request, context):
		erro = self._valida(request)
		if erro:
			return self._status(False, erro, "REBIND", request, context)
		with self.lock:
			now = time.time()
			antigo = self.reg.get(request.name)
			novo = {"host": request.address.host, "port": request.address.port, "registered_at": antigo["registered_at"] if antigo else now, "updated_at": now}
			self.reg[request.name] = novo
			self._salvar()
		if antigo:
			msg = f"'{request.name}' atualizado: {antigo['host']}:{antigo['port']} -> {novo['host']}:{novo['port']}"
		else:
			msg = f"'{request.name}' nao existia; registrado em {novo['host']}:{novo['port']}"
		return self._status(True, msg, "REBIND", request, context)

	def Unbind(self, request, context):
		with self.lock:
			r = self.reg.pop(request.name, None)
			if r:
				self._salvar()
		if r is None:
			return self._status(False, f"nome '{request.name}' nao registrado", "UNBIND", request, context)
		return self._status(True, f"'{request.name}' ({r['host']}:{r['port']}) removido", "UNBIND", request, context)

	def Lookup(self, request, context):
		with self.lock:
			r = self.reg.get(request.name)
		if r is None:
			log(f"LOOKUP  de {context.peer():24} '{request.name}' -> nao encontrado")
			return naming_pb2.LookupReply(found=False, message=f"nome '{request.name}' nao registrado")
		log(f"LOOKUP  de {context.peer():24} '{request.name}' -> {r['host']}:{r['port']}")
		return naming_pb2.LookupReply(found=True, address=naming_pb2.Address(host=r["host"], port=r["port"]))

	def List(self, request, context):
		with self.lock:
			itens = sorted(self.reg.items())
		log(f"LIST    de {context.peer():24} {len(itens)} registro(s)")
		return naming_pb2.ListReply(entries=[
			naming_pb2.Entry(name=n, address=naming_pb2.Address(host=r["host"], port=r["port"]),
				registered_at=r["registered_at"], updated_at=r["updated_at"])
			for n, r in itens])

	@staticmethod
	def _status(ok, msg, op, request, context):
		log(f"{op:7} de {context.peer():24} {'ok  ' if ok else 'ERRO'} {msg}")
		return naming_pb2.Status(ok=ok, message=msg)


def main():
	ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	ap.add_argument("--port", type=int, default=config.NS_PORT)
	ap.add_argument("--db", help="arquivo JSON para persistir os registros (opcional)")
	args = ap.parse_args()

	server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
	naming_pb2_grpc.add_NamingServiceServicer_to_server(NamingService(args.db), server)
	server.add_insecure_port(f"[::]:{args.port}")
	server.start()
	log(f"servico de nomes em {config.HOSTNAME} ({config.ip_local('8.8.8.8', 53)}) porta {args.port}")
	signal.signal(signal.SIGTERM, lambda *_: server.stop(1))
	try:
		server.wait_for_termination()
	except KeyboardInterrupt:
		server.stop(1)
	log("servico de nomes encerrado")


if __name__ == "__main__":
	main()
