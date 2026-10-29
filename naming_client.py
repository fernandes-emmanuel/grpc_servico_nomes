"""Cliente do Servico de Nomes (usado pelos servidores, pelo cliente e como ferramenta de linha de comando).

Uso:  python3 naming_client.py [--ns HOST:PORTA] list
      python3 naming_client.py lookup calculadora
      python3 naming_client.py bind   teste 10.0.0.5:9000
      python3 naming_client.py rebind teste 10.0.0.6:9000
      python3 naming_client.py unbind teste
"""
import argparse
import sys
import time

import grpc

import config
import naming_pb2
import naming_pb2_grpc


class NameNotFound(Exception):
	pass


class NamingClient:
	def __init__(self, host=config.NS_HOST, port=config.NS_PORT, timeout=config.RPC_TIMEOUT):
		self.target = f"{host}:{port}"
		self.timeout = timeout
		self.channel = grpc.insecure_channel(self.target)
		self.stub = naming_pb2_grpc.NamingServiceStub(self.channel)

	def bind(self, name, host, port):
		return self.stub.Bind(naming_pb2.BindRequest(name=name, address=naming_pb2.Address(host=host, port=port)), timeout=self.timeout)

	def rebind(self, name, host, port):
		return self.stub.Rebind(naming_pb2.BindRequest(name=name, address=naming_pb2.Address(host=host, port=port)), timeout=self.timeout)

	def unbind(self, name):
		return self.stub.Unbind(naming_pb2.NameRequest(name=name), timeout=self.timeout)

	def lookup(self, name):
		r = self.stub.Lookup(naming_pb2.NameRequest(name=name), timeout=self.timeout)
		if not r.found:
			raise NameNotFound(r.message)
		return f"{r.address.host}:{r.address.port}"

	def list(self):
		return self.stub.List(naming_pb2.Empty(), timeout=self.timeout).entries

	def close(self):
		self.channel.close()


def parse_ns(s):
	host, _, port = s.rpartition(":")
	return host or config.NS_HOST, int(port or config.NS_PORT)


def main():
	ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	ap.add_argument("--ns", default=f"{config.NS_HOST}:{config.NS_PORT}", help="endereco do servico de nomes")
	ap.add_argument("op", choices=["bind", "rebind", "unbind", "lookup", "list"])
	ap.add_argument("name", nargs="?")
	ap.add_argument("address", nargs="?", help="HOST:PORTA (bind/rebind)")
	args = ap.parse_args()
	if args.op != "list" and not args.name:
		ap.error("informe o nome")
	if args.op in ("bind", "rebind") and not args.address:
		ap.error("informe o endereco HOST:PORTA")

	ns = NamingClient(*parse_ns(args.ns))
	try:
		if args.op == "list":
			for e in ns.list():
				print(f"{e.name:15} {e.address.host}:{e.address.port:<6} atualizado {time.strftime('%H:%M:%S', time.localtime(e.updated_at))}")
		elif args.op == "lookup":
			print(ns.lookup(args.name))
		elif args.op == "unbind":
			r = ns.unbind(args.name)
			print(("ok: " if r.ok else "ERRO: ") + r.message)
			sys.exit(0 if r.ok else 1)
		else:
			host, port = parse_ns(args.address)
			r = getattr(ns, args.op)(args.name, host, port)
			print(("ok: " if r.ok else "ERRO: ") + r.message)
			sys.exit(0 if r.ok else 1)
	except NameNotFound as e:
		sys.exit(f"ERRO: {e}")
	except grpc.RpcError as e:
		sys.exit(f"ERRO: servico de nomes {ns.target} indisponivel ({e.code().name})")


if __name__ == "__main__":
	main()
