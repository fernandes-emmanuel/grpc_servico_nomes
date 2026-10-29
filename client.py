"""Cliente: descobre o endereco dos dois servicos no Servico de Nomes (lookup) e faz requisicoes a eles.

Uso:  python3 client.py [--ns HOST:PORTA] --demo          sequencia de demonstracao
      python3 client.py [--ns HOST:PORTA] COMANDO ...     um comando
      python3 client.py [--ns HOST:PORTA]                 modo interativo

Comandos:
  soma|sub|mul|div|pot|mod A B   calculadora: operacao binaria
  avaliar EXPRESSAO              calculadora: expressao, ex. "(2+3)*7**2"
  put CHAVE VALOR                armazenamento: grava
  get CHAVE                      armazenamento: le
  del CHAVE                      armazenamento: remove
  listar                         armazenamento: lista os pares
  stats                          estatisticas dos dois servidores
  nomes                          registros do servico de nomes
  sair
"""
import argparse
import shlex
import sys
import time

import grpc

import config
import naming_client
import servicos_pb2
import servicos_pb2_grpc

VAZIO = servicos_pb2.Vazio()
METADADOS = (("cliente", config.HOSTNAME),)


class ServicoRemoto:

	def __init__(self, ns, nome, classe_stub):
		self.ns, self.nome, self.classe_stub = ns, nome, classe_stub
		self.endereco = self.canal = self.stub = None

	def _conectar(self):
		endereco = self.ns.lookup(self.nome)
		print(f"  [lookup] '{self.nome}' -> {endereco}")
		if endereco != self.endereco:
			if self.canal:
				self.canal.close()
			self.endereco = endereco
			self.canal = grpc.insecure_channel(endereco)
			self.stub = self.classe_stub(self.canal)

	def chamar(self, metodo, requisicao):
		for tentativa in (1, 2):
			if self.stub is None:
				self._conectar()
			try:
				t0 = time.perf_counter()
				r = getattr(self.stub, metodo)(requisicao, timeout=config.RPC_TIMEOUT, metadata=METADADOS)
				self.rtt = (time.perf_counter() - t0) * 1000
				return r
			except grpc.RpcError as e:
				if e.code() not in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED) or tentativa == 2:
					raise
				print(f"  [falha] '{self.nome}' em {self.endereco} nao respondeu ({e.code().name}); refazendo lookup")
				self.stub = None


class Cliente:
	def __init__(self, ns_host, ns_port):
		self.ns = naming_client.NamingClient(ns_host, ns_port)
		self.calc = ServicoRemoto(self.ns, config.CALC_NAME, servicos_pb2_grpc.CalculadoraStub)
		self.kv = ServicoRemoto(self.ns, config.KV_NAME, servicos_pb2_grpc.ArmazenamentoStub)

	def executar(self, partes):
		cmd, args = partes[0].lower(), partes[1:]
		if cmd in ("soma", "sub", "mul", "div", "pot", "mod"):
			a, b = map(float, args)
			self._resultado(self.calc.chamar("Calcular", servicos_pb2.Operacao(op=cmd, a=a, b=b)), self.calc)
		elif cmd == "avaliar":
			self._resultado(self.calc.chamar("Avaliar", servicos_pb2.Expressao(texto=" ".join(args))), self.calc)
		elif cmd == "put":
			chave, valor = args[0], " ".join(args[1:])
			self._resposta(self.kv.chamar("Put", servicos_pb2.Par(chave=chave, valor=valor)))
		elif cmd == "get":
			self._resposta(self.kv.chamar("Get", servicos_pb2.Chave(chave=args[0])), mostrar_valor=True)
		elif cmd in ("del", "delete"):
			self._resposta(self.kv.chamar("Delete", servicos_pb2.Chave(chave=args[0])))
		elif cmd == "listar":
			r = self.kv.chamar("Listar", VAZIO)
			print(f"  {len(r.pares)} par(es) em {r.servidor} ({self.kv.rtt:.2f} ms)")
			for p in r.pares:
				print(f"    {p.chave} = {p.valor}")
		elif cmd == "stats":
			for servico in (self.calc, self.kv):
				s = servico.chamar("Estatisticas", VAZIO)
				print(f"  {servico.nome} @ {s.servidor} ({s.endereco}): {s.requisicoes} requisicoes em {s.uptime:.1f}s")
				print(f"    por metodo:  {dict(s.por_metodo)}")
				print(f"    por cliente: {dict(s.por_cliente)}")
		elif cmd == "nomes":
			registros = self.ns.list()
			if not registros:
				print("  (nenhum registro)")
			for e in registros:
				print(f"  {e.name:15} {e.address.host}:{e.address.port}")
		else:
			raise ValueError(f"comando desconhecido '{cmd}'")

	@staticmethod
	def _resultado(r, servico):
		if r.ok:
			print(f"  = {r.valor:g}   (calculado por {r.servidor}, {servico.rtt:.2f} ms)")
		else:
			print(f"  ERRO: {r.erro}   (servidor {r.servidor})")

	def _resposta(self, r, mostrar_valor=False):
		texto = f"  {r.valor}" if mostrar_valor and r.ok else f"  {'ok' if r.ok else 'ERRO'}: {r.mensagem}"
		print(f"{texto}   (servidor {r.servidor}, {self.kv.rtt:.2f} ms)")

	def tratar(self, partes):
		try:
			self.executar(partes)
			return True
		except naming_client.NameNotFound as e:
			print(f"  ERRO no lookup: {e}")
		except grpc.RpcError as e:
			print(f"  ERRO remoto: {e.code().name} - {e.details()}")
		except (ValueError, IndexError):
			print("  uso invalido (digite 'ajuda')")
		return False

DEMO = [
	"nomes",
	"soma 2 3", "div 10 4", "pot 2 10", "div 1 0", "avaliar (2+3)*7**2", "avaliar \"__import__('os')\"",
	"put curso SistemasDistribuidos", "put middleware gRPC", "put middleware gRPC+ServicoDeNomes",
	"get middleware", "get inexistente", "listar", "del curso", "listar",
	"stats",
]


def main():
	ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	ap.add_argument("--ns", default=f"{config.NS_HOST}:{config.NS_PORT}", help="endereco do servico de nomes HOST:PORTA")
	ap.add_argument("--demo", action="store_true", help="executa uma sequencia de demonstracao")
	ap.add_argument("comando", nargs=argparse.REMAINDER)
	args = ap.parse_args()
	cli = Cliente(*naming_client.parse_ns(args.ns))
	print(f"cliente {config.HOSTNAME} - servico de nomes em {cli.ns.target}")

	if args.demo:
		ok = True
		for linha in DEMO:
			print(f"> {linha}")
			ok = cli.tratar(shlex.split(linha)) and ok
		sys.exit(0 if ok else 1)
	if args.comando:
		sys.exit(0 if cli.tratar(args.comando) else 1)

	tty = sys.stdin.isatty()
	if tty:
		print("modo interativo (digite 'ajuda' ou 'sair')")
	while True:
		try:
			linha = input("> " if tty else "").strip()
		except (EOFError, KeyboardInterrupt):
			break
		if not linha:
			continue
		if not tty:
			print(f"> {linha}")
		if linha in ("sair", "exit", "quit"):
			break
		if linha in ("ajuda", "help"):
			print(__doc__.split("Comandos:")[1])
			continue
		try:
			cli.tratar(shlex.split(linha))
		except ValueError as e:
			print(f"  {e}")


if __name__ == "__main__":
	main()
