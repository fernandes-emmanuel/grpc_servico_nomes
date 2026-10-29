# Serviço de Nomes e serviços remotos em gRPC

- **Serviço de Nomes** (`naming_server.py`): `bind`, `lookup`, `unbind`, `rebind` (e `list`).
- **Serviço 1 – Calculadora** (`calc_server.py`): `Calcular(op, a, b)`, `Avaliar(expressão)`, `Estatisticas()`.
- **Serviço 2 – Armazenamento chave-valor** (`kv_server.py`): `Put`, `Get`, `Delete`, `Listar`, `Estatisticas()`.
- **Cliente** (`client.py`): conhece apenas o endereço do serviço de nomes; descobre os serviços com `lookup` e faz as requisições.

Interfaces em [`protos/naming.proto`](protos/naming.proto) e [`protos/servicos.proto`](protos/servicos.proto).

Ao iniciar, cada servidor faz `bind` do seu nome e endereço (ou `rebind`, se o nome já estiver registrado) e, ao encerrar, faz `unbind`. O cliente guarda o endereço obtido no `lookup`; se o servidor deixar de responder, refaz o `lookup`.

## Instalação

```bash
git clone https://github.com/fernandes-emmanuel/grpc_servico_nomes.git
cd grpc_servico_nomes
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Para regenerar os stubs: `bash gerar_stubs.sh`.

## Execução

Cada componente em uma máquina (`IP_NS` = IP da máquina do serviço de nomes):

```bash
python3 naming_server.py --port 5678
```

```bash
python3 calc_server.py --ns IP_NS:5678
```

```bash
python3 kv_server.py --ns IP_NS:5678
```

```bash
python3 client.py --ns IP_NS:5678 --demo
python3 client.py --ns IP_NS:5678 avaliar "(2+3)*7**2"
python3 client.py --ns IP_NS:5678
```

Comandos do cliente: `soma|sub|mul|div|pot|mod A B`, `avaliar EXPR`, `put CHAVE VALOR`, `get CHAVE`, `del CHAVE`, `listar`, `stats`, `nomes`, `sair`.

Operações do serviço de nomes pela linha de comando:

```bash
python3 naming_client.py --ns IP_NS:5678 bind   teste 10.0.0.5:9000
python3 naming_client.py --ns IP_NS:5678 lookup teste
python3 naming_client.py --ns IP_NS:5678 rebind teste 10.0.0.6:9000
python3 naming_client.py --ns IP_NS:5678 unbind teste
python3 naming_client.py --ns IP_NS:5678 list
```

Testes: `bash teste_local.sh` (uma máquina) e `bash docker/teste_multihost.sh` (um container com IP próprio por componente). Saídas em [`resultados/`](resultados).

## Resultados

Serviço de nomes `172.29.0.10`, calculadora `172.29.0.20` (depois `172.29.0.21`), armazenamento `172.29.0.30`, clientes `172.29.0.40` e `172.29.0.41`.

```
> nomes
  armazenamento   172.29.0.30:36645
  calculadora     172.29.0.20:50051
> soma 2 3
  [lookup] 'calculadora' -> 172.29.0.20:50051
  = 5   (calculado por maquina-calc1, 2.95 ms)
> put curso SistemasDistribuidos
  [lookup] 'armazenamento' -> 172.29.0.30:36645
  ok: PUT 'curso' = 'SistemasDistribuidos' (criada)   (servidor maquina-kv, 2.84 ms)
```

Calculadora muda de máquina (`rebind`) e o cliente refaz o `lookup`:

```
[maquina-calc2] rebind no servico de nomes 172.29.0.10:5678: 'calculadora' atualizado: 172.29.0.20:50051 -> 172.29.0.21:50051

> avaliar 2**8
  [falha] 'calculadora' em 172.29.0.20:50051 nao respondeu (DEADLINE_EXCEEDED); refazendo lookup
  [lookup] 'calculadora' -> 172.29.0.21:50051
  = 256   (calculado por maquina-calc2, 6.29 ms)
```

Operações do serviço de nomes:

```
$ naming_client.py bind calculadora 1.2.3.4:9999
ERRO: nome 'calculadora' ja registrado em 172.29.0.21:50051 (use rebind)
$ naming_client.py bind teste 172.29.0.99:7000
ok: 'teste' -> 172.29.0.99:7000
$ naming_client.py rebind teste 172.29.0.98:7001
ok: 'teste' atualizado: 172.29.0.99:7000 -> 172.29.0.98:7001
$ naming_client.py lookup teste
172.29.0.98:7001
$ naming_client.py unbind teste
ok: 'teste' (172.29.0.98:7001) removido
$ naming_client.py lookup teste
ERRO: nome 'teste' nao registrado
```
