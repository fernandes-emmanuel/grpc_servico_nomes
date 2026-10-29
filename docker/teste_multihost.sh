#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.."
ROOT=$(pwd)
OUT=$ROOT/resultados
IMAGE=${IMAGE:-grpc-lab}
NET=grpcnet
NS=172.29.0.10
mkdir -p "$OUT"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
	docker build -t "$IMAGE" -f docker/Dockerfile .
fi
docker network inspect $NET >/dev/null 2>&1 || docker network create --subnet 172.29.0.0/16 $NET >/dev/null

opts() { echo --name "$1" --hostname "$1" --network $NET --ip "$2" -v "$ROOT":/app:ro -w /app -e PYTHONUNBUFFERED=1 -e NS_HOST=$NS; }
run() { local n=$1 ip=$2; shift 2; docker rm -f "$n" >/dev/null 2>&1; docker run -d $(opts "$n" "$ip") "$IMAGE" "$@" >/dev/null; }
exec_fg() { local n=$1 ip=$2; shift 2; docker rm -f "$n" >/dev/null 2>&1; docker run --rm -i $(opts "$n" "$ip") "$IMAGE" "$@"; }
cleanup() { docker rm -f $(docker ps -aq --filter network=$NET) >/dev/null 2>&1; }
cleanup

echo "### subindo servico de nomes e os dois servicos em maquinas diferentes"
run servico-nomes $NS python3 naming_server.py
run maquina-calc1 172.29.0.20 python3 calc_server.py
run maquina-kv 172.29.0.30 python3 kv_server.py --port 0
sleep 3

echo; echo "### cliente1 (172.29.0.40): demonstracao"
exec_fg cliente1 172.29.0.40 python3 client.py --demo </dev/null | tee "$OUT/cliente1_demo.txt"

echo; echo "### cliente2 (172.29.0.41) com endereco em cache; a calculadora migra para maquina-calc2"
{
	echo "avaliar 6*7"
	sleep 6
	echo "avaliar 2**8"
	echo "stats"
} | exec_fg cliente2 172.29.0.41 python3 client.py > "$OUT/cliente2_migracao.txt" &
CLI2=$!
sleep 3
run maquina-calc2 172.29.0.21 python3 calc_server.py
sleep 2
docker kill maquina-calc1 >/dev/null
wait $CLI2
cat "$OUT/cliente2_migracao.txt"

echo; echo "### ferramenta de linha de comando do servico de nomes (de cliente1)"
{
	for c in "list" "lookup calculadora" "bind calculadora 1.2.3.4:9999" "bind teste 172.29.0.99:7000" \
		"rebind teste 172.29.0.98:7001" "lookup teste" "unbind teste" "unbind teste" "lookup teste"; do
		echo "\$ naming_client.py $c"
		exec_fg cliente1 172.29.0.40 python3 naming_client.py $c </dev/null 2>&1
	done
} | tee "$OUT/naming_client.txt"

echo; echo "### encerrando os servidores (SIGTERM -> unbind)"
docker stop maquina-calc2 maquina-kv >/dev/null
exec_fg cliente1 172.29.0.40 python3 client.py nomes </dev/null
exec_fg cliente1 172.29.0.40 python3 client.py soma 1 1 </dev/null

docker stop servico-nomes >/dev/null
for c in servico-nomes maquina-calc1 maquina-calc2 maquina-kv; do docker logs $c > "$OUT/$c.txt" 2>&1; done
cleanup
echo; echo "logs em resultados/"
