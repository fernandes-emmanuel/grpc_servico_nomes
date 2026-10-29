"""Servico 2 - Armazenamento chave-valor remoto (gRPC), registrado no servico de nomes.

Uso:  python3 kv_server.py [--ns HOST:PORTA] [--port 50052] [--advertise IP] [--name armazenamento]
"""
import threading

import config
import servicos_pb2
import servicos_pb2_grpc
import servidor_base
from config import log


class Armazenamento(servicos_pb2_grpc.ArmazenamentoServicer):
	def __init__(self, stats):
		self.stats = stats
		self.lock = threading.Lock()
		self.dados = {}

	def _resposta(self, cliente, ok, valor="", mensagem=""):
		log(f"{cliente:12} {'ok  ' if ok else 'ERRO'} {mensagem}")
		return servicos_pb2.Resposta(ok=ok, valor=valor, mensagem=mensagem, servidor=config.HOSTNAME)

	def Put(self, request, context):
		cliente = self.stats.conta("Put", context)
		if not request.chave:
			return self._resposta(cliente, False, mensagem="PUT: chave vazia")
		with self.lock:
			antigo = self.dados.get(request.chave)
			self.dados[request.chave] = request.valor
		acao = "atualizada" if antigo is not None else "criada"
		return self._resposta(cliente, True, antigo or "", f"PUT {request.chave!r} = {request.valor!r} ({acao})")

	def Get(self, request, context):
		cliente = self.stats.conta("Get", context)
		with self.lock:
			valor = self.dados.get(request.chave)
		if valor is None:
			return self._resposta(cliente, False, mensagem=f"GET {request.chave!r}: chave inexistente")
		return self._resposta(cliente, True, valor, f"GET {request.chave!r} -> {valor!r}")

	def Delete(self, request, context):
		cliente = self.stats.conta("Delete", context)
		with self.lock:
			valor = self.dados.pop(request.chave, None)
		if valor is None:
			return self._resposta(cliente, False, mensagem=f"DELETE {request.chave!r}: chave inexistente")
		return self._resposta(cliente, True, valor, f"DELETE {request.chave!r} (era {valor!r})")

	def Listar(self, request, context):
		cliente = self.stats.conta("Listar", context)
		with self.lock:
			pares = [servicos_pb2.Par(chave=k, valor=v) for k, v in sorted(self.dados.items())]
		log(f"{cliente:12} ok   LISTAR {len(pares)} par(es)")
		return servicos_pb2.ListaPares(pares=pares, servidor=config.HOSTNAME)

	def Estatisticas(self, request, context):
		self.stats.conta("Estatisticas", context)
		return self.stats.mensagem()


def main():
	args = servidor_base.argumentos(__doc__, config.KV_NAME, config.KV_PORT)
	stats = servidor_base.Estatisticas()
	servidor_base.executar(args, lambda s: servicos_pb2_grpc.add_ArmazenamentoServicer_to_server(Armazenamento(stats), s), stats)


if __name__ == "__main__":
	main()
