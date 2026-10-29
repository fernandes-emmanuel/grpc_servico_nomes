"""Partes comuns aos dois servidores de aplicacao: estatisticas, registro no
servico de nomes (bind/rebind) ao iniciar e unbind ao encerrar."""
import argparse
import signal
import threading
import time
from concurrent import futures

import grpc

import config
import naming_client
import servicos_pb2
from config import log


class Estatisticas:
	def __init__(self):
		self.lock = threading.Lock()
		self.inicio = time.time()
		self.total = 0
		self.por_metodo = {}
		self.por_cliente = {}
		self.endereco = ""

	def conta(self, metodo, context):
		cliente = dict(context.invocation_metadata()).get("cliente") or context.peer()
		with self.lock:
			self.total += 1
			self.por_metodo[metodo] = self.por_metodo.get(metodo, 0) + 1
			self.por_cliente[cliente] = self.por_cliente.get(cliente, 0) + 1
		return cliente

	def mensagem(self):
		with self.lock:
			return servicos_pb2.Stats(servidor=config.HOSTNAME, endereco=self.endereco,
				uptime=time.time() - self.inicio, requisicoes=self.total,
				por_metodo=self.por_metodo, por_cliente=self.por_cliente)


def argumentos(descricao, nome, porta):
	ap = argparse.ArgumentParser(description=descricao)
	ap.add_argument("--name", default=nome, help=f"nome registrado no servico de nomes (padrao: {nome})")
	ap.add_argument("--port", type=int, default=porta, help="porta de escuta (0 = qualquer porta livre)")
	ap.add_argument("--advertise", help="host/IP anunciado no servico de nomes (padrao: IP local usado para alcancar o servico de nomes; na AWS use o IP privado ou publico)")
	ap.add_argument("--ns", default=f"{config.NS_HOST}:{config.NS_PORT}", help="endereco do servico de nomes HOST:PORTA")
	ap.add_argument("--no-unbind", action="store_true", help="nao remover o registro ao encerrar (simula uma queda do servidor)")
	return ap.parse_args()


def executar(args, registrar_servicer, stats):
	ns_host, ns_port = naming_client.parse_ns(args.ns)
	server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
	registrar_servicer(server)
	porta = server.add_insecure_port(f"[::]:{args.port}")
	server.start()

	host = args.advertise or config.ip_local(ns_host, ns_port)
	stats.endereco = f"{host}:{porta}"
	log(f"servidor '{args.name}' em {config.HOSTNAME}, escutando na porta {porta}")

	ns = naming_client.NamingClient(ns_host, ns_port)
	for tentativa in range(1, 11):
		try:
			r = ns.bind(args.name, host, porta)
			if r.ok:
				log(f"bind   no servico de nomes {ns.target}: {r.message}")
			else:
				log(f"bind   recusado: {r.message}")
				r = ns.rebind(args.name, host, porta)
				log(f"rebind no servico de nomes {ns.target}: {r.message}")
			break
		except grpc.RpcError as e:
			log(f"servico de nomes {ns.target} indisponivel ({e.code().name}), tentativa {tentativa}/10")
			time.sleep(1)
	else:
		server.stop(0)
		raise SystemExit("ERRO: nao foi possivel registrar no servico de nomes")

	parar = threading.Event()
	signal.signal(signal.SIGTERM, lambda *_: parar.set())
	signal.signal(signal.SIGINT, lambda *_: parar.set())
	parar.wait()

	if not args.no_unbind:
		try:
			if ns.lookup(args.name) == stats.endereco:
				log(f"unbind no servico de nomes: {ns.unbind(args.name).message}")
			else:
				log("registro aponta para outro servidor; unbind nao realizado")
		except (grpc.RpcError, naming_client.NameNotFound) as e:
			log(f"unbind nao realizado: {e}")
	server.stop(1).wait()
	log("servidor encerrado")
