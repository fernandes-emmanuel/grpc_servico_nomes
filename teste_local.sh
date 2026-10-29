#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"
PY=${PY:-python3}
export NS_HOST=localhost NS_PORT=${NS_PORT:-5678}

$PY naming_server.py & NS=$!
sleep 1
$PY calc_server.py --advertise localhost & CALC=$!
$PY kv_server.py --advertise localhost --port 0 & KV=$!
sleep 1.5

echo; echo "### cliente (demo)"
$PY client.py --demo

echo; echo "### calculadora muda de endereco: nova instancia faz rebind, a antiga 'cai' sem unbind"
$PY calc_server.py --advertise localhost --port 50061 & CALC2=$!
sleep 1.5
kill -9 $CALC
$PY client.py avaliar "1+1"

echo; echo "### unbind manual e lookup de nome removido"
$PY naming_client.py unbind armazenamento
$PY client.py get x

echo; echo "### encerramento: os servidores fazem unbind"
kill $KV $CALC2; wait $KV $CALC2 2>/dev/null
$PY naming_client.py list
kill $NS; wait $NS 2>/dev/null
echo; echo "ok"
