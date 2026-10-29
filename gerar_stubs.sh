#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m grpc_tools.protoc -Iprotos --python_out=. --grpc_python_out=. protos/naming.proto protos/servicos.proto
echo "stubs gerados: $(ls *_pb2*.py | tr '\n' ' ')"
