"""Servico 1 - Calculadora remota (gRPC), registrada no servico de nomes.

Uso:  python3 calc_server.py [--ns HOST:PORTA] [--port 50051] [--advertise IP] [--name calculadora]
"""
import ast
import math
import operator

import config
import servicos_pb2
import servicos_pb2_grpc
import servidor_base
from config import log

OPERACOES = {
	"SOMA": operator.add, "SUB": operator.sub, "MUL": operator.mul,
	"DIV": operator.truediv, "POT": operator.pow, "MOD": operator.mod,
}
OPS_AST = {
	ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
	ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
	ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def avaliar(expr):
	def ev(node):
		if isinstance(node, ast.Constant) and type(node.value) in (int, float):
			return node.value
		if isinstance(node, ast.BinOp) and type(node.op) in OPS_AST:
			if isinstance(node.op, ast.Pow) and abs(ev(node.right)) > 100:
				raise ValueError("expoente muito grande")
			return OPS_AST[type(node.op)](ev(node.left), ev(node.right))
		if isinstance(node, ast.UnaryOp) and type(node.op) in OPS_AST:
			return OPS_AST[type(node.op)](ev(node.operand))
		raise ValueError("expressao invalida")
	return ev(ast.parse(expr, mode="eval").body)


class Calculadora(servicos_pb2_grpc.CalculadoraServicer):
	def __init__(self, stats):
		self.stats = stats

	def _resultado(self, cliente, descricao, func):
		try:
			valor = float(func())
			if math.isinf(valor) or math.isnan(valor):
				raise ValueError("resultado fora do intervalo")
			r = servicos_pb2.Resultado(ok=True, valor=valor, servidor=config.HOSTNAME)
			log(f"{cliente:12} {descricao} = {valor:g}")
		except (ArithmeticError, ValueError, SyntaxError, TypeError) as e:
			r = servicos_pb2.Resultado(ok=False, erro=f"{type(e).__name__}: {e}", servidor=config.HOSTNAME)
			log(f"{cliente:12} {descricao} -> ERRO {r.erro}")
		return r

	def Calcular(self, request, context):
		cliente = self.stats.conta("Calcular", context)
		op = request.op.upper()
		def f():
			if op not in OPERACOES:
				raise ValueError(f"operacao desconhecida '{request.op}' (use {', '.join(OPERACOES)})")
			if op == "POT" and abs(request.b) > 100:
				raise ValueError("expoente muito grande")
			return OPERACOES[op](request.a, request.b)
		return self._resultado(cliente, f"{op} {request.a:g} {request.b:g}", f)

	def Avaliar(self, request, context):
		cliente = self.stats.conta("Avaliar", context)
		return self._resultado(cliente, repr(request.texto), lambda: avaliar(request.texto))

	def Estatisticas(self, request, context):
		self.stats.conta("Estatisticas", context)
		return self.stats.mensagem()


def main():
	args = servidor_base.argumentos(__doc__, config.CALC_NAME, config.CALC_PORT)
	stats = servidor_base.Estatisticas()
	servidor_base.executar(args, lambda s: servicos_pb2_grpc.add_CalculadoraServicer_to_server(Calculadora(stats), s), stats)


if __name__ == "__main__":
	main()
