# Serviço de Nomes + dois serviços remotos em gRPC

Implementação, em **gRPC (Python)**, de:

1. um **Serviço de Nomes** com as operações `bind`, `lookup`, `unbind` e `rebind` (e um `list` extra),
   baseado no [gRPC-SimpleNamingService](https://github.com/professorfabio/gRPC-SimpleNamingService);
2. **dois serviços de aplicação** para acesso remoto, cada um em seu processo/máquina:
   - **Calculadora** (`calc_server.py`) — operações binárias e avaliação segura de expressões;
   - **Armazenamento chave-valor** (`kv_server.py`) — `Put`, `Get`, `Delete`, `Listar`;
3. um **cliente** (`client.py`) que só conhece o endereço do serviço de nomes, descobre o
   endereço dos dois serviços por `lookup` e faz requisições a eles.

```
                         ┌──────────────────────────┐
         (1) bind/rebind │   Serviço de Nomes       │ (1) bind/rebind
       ┌────────────────▶│   naming_server.py :5678 │◀────────────────┐
       │  (4) unbind     │ calculadora -> IP1:50051 │   (4) unbind     │
       │                 │ armazenamento -> IP2:... │                  │
       │                 └──────────────────────────┘                  │
       │                        ▲  (2) lookup("calculadora")           │
┌──────┴────────┐               │      lookup("armazenamento")  ┌──────┴────────┐
│ Calculadora   │        ┌──────┴──────┐                        │ Armazenamento │
│ calc_server   │◀───────│   cliente   │───────────────────────▶│ kv_server     │
│ máquina 1     │ (3) RPC│  client.py  │ (3) RPC                │ máquina 2     │
└───────────────┘        └─────────────┘                        └───────────────┘
```

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| [`protos/naming.proto`](protos/naming.proto) | interface do serviço de nomes (`Bind`, `Lookup`, `Unbind`, `Rebind`, `List`) |
| [`protos/servicos.proto`](protos/servicos.proto) | interfaces dos serviços `Calculadora` e `Armazenamento` |
| `*_pb2.py`, `*_pb2_grpc.py` | stubs gerados pelo `protoc` (regenerar com `bash gerar_stubs.sh`) |
| [`naming_server.py`](naming_server.py) | servidor do serviço de nomes |
| [`naming_client.py`](naming_client.py) | biblioteca cliente do serviço de nomes + ferramenta de linha de comando |
| [`servidor_base.py`](servidor_base.py) | código comum aos servidores: registro (bind/rebind) ao iniciar, unbind ao encerrar, estatísticas |
| [`calc_server.py`](calc_server.py) | serviço 1: calculadora |
| [`kv_server.py`](kv_server.py) | serviço 2: armazenamento chave-valor |
| [`client.py`](client.py) | cliente dos dois serviços |
| [`config.py`](config.py) | configuração (variáveis de ambiente `NS_HOST`, `NS_PORT`, ...) |
| [`teste_local.sh`](teste_local.sh) | teste de tudo em uma máquina (processos diferentes) |
| [`docker/teste_multihost.sh`](docker/teste_multihost.sh) | teste com cada componente em um container com IP próprio |
| [`resultados/`](resultados) | saídas reais dos testes |

## Interfaces

### Serviço de Nomes (`naming.proto`)

| RPC | Usado por | Comportamento |
|---|---|---|
| `Bind(nome, endereço)` | servidor | registra o nome. **Falha** se o nome já existir (como no Java RMI) |
| `Lookup(nome)` | cliente | devolve `found=true` e o endereço, ou `found=false` com mensagem de erro |
| `Unbind(nome)` | servidor | remove o registro (falha se o nome não existir) |
| `Rebind(nome, endereço)` | servidor | atualiza o endereço do nome (se não existir, cria) |
| `List()` | qualquer um | extra: lista todos os registros |

O endereço é `Address { string host; int32 port; }`. As operações respondem
`Status { bool ok; string message; }`. Os registros ficam num dicionário protegido por *lock*
(o servidor gRPC atende em várias threads) e podem ser persistidos em JSON com `--db nomes.json`.

Diferenças em relação ao código de referência: `Lookup`/`Unbind`/`Rebind` de nome inexistente
não derrubam o servidor (no original, `reg[0]` gerava `IndexError`), `Bind` não aceita nome
duplicado, endereço é validado, há *lock* para acesso concorrente e o endereço do serviço de
nomes é configurável (no original o IP estava fixo em `const.py`).

### Serviços de aplicação (`servicos.proto`)

| Serviço | RPCs |
|---|---|
| `Calculadora` | `Calcular(op, a, b)` com `SOMA SUB MUL DIV POT MOD`; `Avaliar("(2+3)*7**2")` (via `ast`, sem `eval`); `Estatisticas()` |
| `Armazenamento` | `Put(chave, valor)`, `Get(chave)`, `Delete(chave)`, `Listar()`, `Estatisticas()` |

Toda resposta traz o campo `servidor` (hostname de quem atendeu), para ficar claro que a
requisição foi atendida em outra máquina. `Estatisticas` devolve uptime, número de
requisições por método e **por cliente** (o cliente envia seu hostname como metadado gRPC).

## Funcionamento

**Servidor** (`servidor_base.executar`):
1. sobe o servidor gRPC em `[::]:PORTA` (todas as interfaces; `--port 0` escolhe uma porta livre,
   que só o serviço de nomes vai conhecer);
2. faz `bind(nome, IP:porta)` no serviço de nomes. O IP anunciado é o da interface usada para
   alcançar o serviço de nomes, ou o informado em `--advertise`. Se o nome já estiver
   registrado (um servidor anterior caiu sem `unbind` ou o serviço mudou de máquina), faz
   `rebind`. Se o serviço de nomes ainda não estiver no ar, tenta de novo por 10 s;
3. ao receber `Ctrl+C`/`SIGTERM`, faz `unbind` — mas só se o registro ainda apontar para ele
   (se outro servidor já fez `rebind`, o registro não é apagado). `--no-unbind` simula uma queda.

**Cliente** (`client.py`):
1. só conhece o endereço do serviço de nomes (`--ns` ou `NS_HOST`/`NS_PORT`);
2. na primeira chamada a um serviço faz `lookup(nome)`, abre o canal gRPC e guarda o endereço;
3. se o servidor não responder (`UNAVAILABLE`/`DEADLINE_EXCEEDED`), refaz o `lookup` e tenta de
   novo — assim o cliente acompanha um serviço que mudou de endereço via `rebind`.

## Instalação

Em **cada** máquina:

```bash
git clone https://github.com/fernandes-emmanuel/grpc_servico_nomes.git
cd grpc_servico_nomes
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt   # grpcio, grpcio-tools, protobuf
```

Os stubs gerados já estão no repositório. Para regenerá-los (por exemplo, se a versão do
`grpcio` instalada for mais antiga que a usada para gerá-los):

```bash
bash gerar_stubs.sh
```

## Como executar

Teste rápido numa máquina só:

```bash
bash teste_local.sh
```

Em máquinas diferentes (troque `IP_NS` pelo IP da máquina do serviço de nomes):

```bash
# máquina A — serviço de nomes
python3 naming_server.py --port 5678 --db nomes.json
```

```bash
# máquina B — calculadora
python3 calc_server.py --ns IP_NS:5678
```

```bash
# máquina C — armazenamento
python3 kv_server.py --ns IP_NS:5678
```

```bash
# máquina D — cliente: demonstração, um comando, ou modo interativo
python3 client.py --ns IP_NS:5678 --demo
python3 client.py --ns IP_NS:5678 avaliar "(2+3)*7**2"
python3 client.py --ns IP_NS:5678 put curso SD
python3 client.py --ns IP_NS:5678
```

Em vez de `--ns`, pode-se usar `export NS_HOST=IP_NS`. Comandos do cliente:
`soma|sub|mul|div|pot|mod A B`, `avaliar EXPR`, `put CHAVE VALOR`, `get CHAVE`, `del CHAVE`,
`listar`, `stats`, `nomes`, `sair`.

Operações do serviço de nomes direto pela linha de comando:

```bash
python3 naming_client.py --ns IP_NS:5678 list
python3 naming_client.py --ns IP_NS:5678 bind   teste 10.0.0.5:9000
python3 naming_client.py --ns IP_NS:5678 lookup teste
python3 naming_client.py --ns IP_NS:5678 rebind teste 10.0.0.6:9000
python3 naming_client.py --ns IP_NS:5678 unbind teste
```

### Na AWS

- Libere no *Security Group* as portas **5678** (serviço de nomes), **50051** (calculadora) e
  **50052** (armazenamento) com origem no próprio SG ou no CIDR da VPC (`172.31.0.0/16`).
- Entre instâncias da mesma VPC, use os **IPs privados**. O servidor detecta sozinho o IP
  privado que alcança o serviço de nomes e o registra.
- Se o cliente estiver **fora** da AWS (no seu computador), os servidores precisam registrar o
  **IP público**, porque é esse endereço que o cliente recebe no `lookup`:
  `python3 calc_server.py --ns IP_PUBLICO_NS:5678 --advertise IP_PUBLICO_DA_MAQUINA`.
- O `bind` do socket é sempre em `[::]` (todas as interfaces), porque o IP público não existe
  na interface de rede da VM.

## Testes realizados

[`docker/teste_multihost.sh`](docker/teste_multihost.sh) cria a rede `172.29.0.0/16` e roda cada
componente num container separado, com hostname e IP próprios:

| Container | IP | Papel |
|---|---|---|
| `servico-nomes` | 172.29.0.10 | serviço de nomes |
| `maquina-calc1` | 172.29.0.20 | calculadora |
| `maquina-calc2` | 172.29.0.21 | calculadora (nova instância, para testar `rebind`) |
| `maquina-kv` | 172.29.0.30 | armazenamento (porta aleatória, `--port 0`) |
| `cliente1`, `cliente2` | 172.29.0.40, .41 | clientes |

```bash
bash docker/teste_multihost.sh   # na raiz do repositorio
```

Trechos das saídas obtidas (completas em [`resultados/`](resultados)):

**Cliente descobrindo os serviços** (`cliente1_demo.txt`):
```
> nomes
  armazenamento   172.29.0.30:34737
  calculadora     172.29.0.20:50051
> soma 2 3
  [lookup] 'calculadora' -> 172.29.0.20:50051
  = 5   (calculado por maquina-calc1, 8.38 ms)
> avaliar "__import__('os')"
  ERRO: ValueError: expressao invalida   (servidor maquina-calc1)
> put curso SistemasDistribuidos
  [lookup] 'armazenamento' -> 172.29.0.30:34737
  ok: PUT 'curso' = 'SistemasDistribuidos' (criada)   (servidor maquina-kv, 5.72 ms)
```

**Migração da calculadora com `rebind`** — `maquina-calc2` sobe, o `bind` é recusado e ela faz
`rebind`; depois `maquina-calc1` é derrubada (`docker kill`, sem `unbind`). O `cliente2`, que
tinha o endereço antigo em cache, detecta a falha, refaz o `lookup` e passa a usar a nova máquina:
```
[maquina-calc2] bind   recusado: nome 'calculadora' ja registrado em 172.29.0.20:50051 (use rebind)
[maquina-calc2] rebind no servico de nomes 172.29.0.10:5678: 'calculadora' atualizado: 172.29.0.20:50051 -> 172.29.0.21:50051

> avaliar 6*7
  [lookup] 'calculadora' -> 172.29.0.20:50051
  = 42   (calculado por maquina-calc1, 5.85 ms)
> avaliar 2**8
  [falha] 'calculadora' em 172.29.0.20:50051 nao respondeu (DEADLINE_EXCEEDED); refazendo lookup
  [lookup] 'calculadora' -> 172.29.0.21:50051
  = 256   (calculado por maquina-calc2, 7.00 ms)
```

**As quatro operações pela linha de comando** (`naming_client.txt`):
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

**Encerramento**: com `docker stop` (SIGTERM) os servidores fazem `unbind`; em seguida o
`lookup` do cliente falha com `nome 'calculadora' nao registrado`.

## Observações

- O `lookup` é feito uma vez e o endereço fica em cache: o serviço de nomes não entra no
  caminho de cada requisição. O custo é que o cache pode ficar velho — daí o novo `lookup`
  quando o servidor não responde.
- Um servidor que cai sem `unbind` deixa um registro "órfão". Ele é corrigido quando outra
  instância faz `rebind`; uma melhoria possível seria registros com prazo (*lease*) renovados
  periodicamente pelos servidores.
- O serviço de nomes é um ponto único de falha; poderia ser replicado.
- A comunicação é sem criptografia (`insecure_channel`); em produção usaria TLS.
