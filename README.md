# labdados — SDK Python

SDK oficial dos serviços do **escritório de apoio do LabDados** (FGV Direito SP).

Quatro funções de alto nível, em português, que cobrem os serviços do escritório:

- `labdados.ocr(...)` — OCR de PDFs (texto e markdown).
- `labdados.transcricao(...)` — transcrição (Whisper) e diarização de áudio.
- `labdados.estruturacao(...)` — extração estruturada de campos com LLMs.
- `labdados.analise_viabilidade(...)` — estima volume de processos antes de uma raspagem.

## Como usar — três modos

Você pode rodar o SDK contra **três alvos diferentes**, sem mudar o código da chamada (só o `api_key` / `local`):

| Modo | Para quê | Quem processa | Quem paga |
|---|---|---|---|
| 1. **Nuvem do escritório** | Caso comum: quer processar dados sem instalar nada pesado. | Servidores do escritório (Azure). | Cota mensal vinculada à sua API key. |
| 2. **Local** | Sigilo absoluto, ou já tem GPU/Tesseract/Ollama em casa. | Sua máquina. | Você (CPU/GPU/Ollama/etc.). |
| 3. **Backend local via Docker** | Reproduzir o ambiente do escritório no seu computador (testar mudanças no backend, debugar workflow). | Containers Docker no `localhost`. | Você (CPU + Azure OpenAI se for usar `estruturacao`). |

A diferença está no que você passa pra função:

```python
import labdados

# 1) NUVEM do escritório
labdados.ocr(arquivos="pdfs/", api_key="sk_lab_...", saida="out/")

# 2) LOCAL (no seu computador)
labdados.ocr(arquivos="pdfs/", local=True, saida="out/")

# 3) BACKEND LOCAL via Docker (mesma chamada do modo 1, só muda a URL)
import os
os.environ["LABDADOS_BASE_URL"] = "http://localhost:8000"  # ou 18000 — ver abaixo
labdados.ocr(arquivos="pdfs/", api_key="sk_lab_...", saida="out/")
```

A seção certa pra ler depende do seu caso:

- **Você é pesquisador e só quer extrair dados** → leia [Modo 1 — Nuvem do escritório](#modo-1--nuvem-do-escritório).
- **Quer rodar sem mandar nada pra fora** → leia [Modo 2 — Local](#modo-2--local).
- **Está desenvolvendo / quer simular o escritório no seu PC** → leia [Modo 3 — Backend local via Docker](#modo-3--backend-local-via-docker).

---

## Instalação

Requer **Python ≥ 3.11**.

```bash
pip install labdados                    # base (apenas Modos 1 e 3)
pip install labdados[ocr]               # + OCR local (PyMuPDF + Tesseract)
pip install labdados[transcricao]       # + transcrição local (faster-whisper)
pip install labdados[estruturacao]      # + estruturação local (cliente OpenAI-compat)
pip install labdados[viabilidade]       # + análise de viabilidade (juscraper + Quarto)
pip install labdados[all]               # tudo
```

Os extras só são necessários para o **Modo 2 (local)**. Os modos 1 e 3 só precisam do pacote base — o processamento pesado fica no servidor.

---

## Modo 1 — Nuvem do escritório

Use quando você só quer **mandar os arquivos e receber o resultado** sem instalar nada pesado. É o caminho default.

### 1. Pegue uma API key

Peça uma no portal do escritório:

<https://labdados-frontend.livelydesert-3e3e3dd8.brazilsouth.azurecontainerapps.io/consultoria/api-key>

Você preenche um formulário curto, o admin aprova, e o token (algo como `sk_lab_xxx...`) chega por e-mail. Esse token é **secreto** — guarde como senha.

### 2. Use

```python
import labdados

labdados.ocr(
    arquivos="meus_pdfs/",          # arquivo, lista ou pasta
    api_key="sk_lab_...",
    modelo="pymupdf-tesseract",     # ou "paddleocr" (mais preciso)
    formato="txt",                  # ou "md"
    idiomas="por+eng",
    saida="resultados/",
)

labdados.transcricao(
    arquivos="reuniao.mp3",
    api_key="sk_lab_...",
    modelo="whisperx",              # com diarização
    diarizacao=True,
    saida="resultados/",
)

labdados.estruturacao(
    arquivos="acordaos.csv",
    coluna_texto="ementa",
    api_key="sk_lab_...",
    schema={
        "type": "object",
        "properties": {
            "autor": {"type": "string"},
            "valor_causa": {"type": "number"},
        },
        "required": ["autor"],
    },
    saida="resultados/",
)
```

Cada chamada faz upload, dispara o processamento, faz polling até concluir e baixa o resultado em `saida/` (geralmente um `.zip`).

### Cliente reutilizável

Se for fazer várias chamadas, crie um `Client` uma vez:

```python
client = labdados.Client(api_key="sk_lab_...")
client.ocr(arquivos="pdfs/", saida="out_pdf/")
client.transcricao(arquivos="audios/", saida="out_audio/", modelo="whisperx", diarizacao=True)
client.test_connection()                # confirma que a key tá ok
```

### Cota mensal

Cada API key tem cota mensal em reais (default R$ 50/mês). O backend estima o custo antes de aceitar e pode rejeitar / truncar arquivos. Veja seu uso em `Client.test_connection()` ou no portal.

---

## Modo 2 — Local

Use quando o dado é **sigiloso** (não pode sair da sua máquina) ou quando você já tem GPU / Tesseract / Ollama instalado e prefere usar.

Não precisa de API key — `local=True` já basta.

### Requisitos por serviço

- **OCR local** — `pip install labdados[ocr]` + Tesseract no SO
  ([instalador](https://tesseract-ocr.github.io)). No Windows, o SDK
  procura em `C:\Program Files\Tesseract-OCR\tesseract.exe` automaticamente; em outro path, defina `TESSERACT_CMD`.
- **Transcrição local** — `pip install labdados[transcricao]`. Roda em CPU (lento) ou GPU CUDA (se torch detectar). **Sem diarização local** — para diarizar, use o modo nuvem com `modelo="whisperx"`.
- **Estruturação local** — `pip install labdados[estruturacao]`. Espera um servidor OpenAI-compatible no `base_url_local`. Default: [Ollama](https://ollama.com) em `http://localhost:11434/v1`. Funciona também com OpenAI direto, Azure OpenAI, vLLM, LM Studio.
- **Viabilidade** — `pip install labdados[viabilidade]`. Usa juscraper + Datajud direto da sua máquina (precisa de internet). Para gerar PDF, instale o binário do [Quarto](https://quarto.org).

### Exemplos

```python
# OCR local
labdados.ocr(
    arquivos="pdfs_sensiveis/",
    local=True,
    modelo="pymupdf-tesseract",
    saida="out/",
)

# Transcrição local com modelo small (CPU)
labdados.transcricao(
    arquivos="reuniao.mp3",
    local=True,
    modelo_local="small",       # ou "tiny", "base", "medium", "large-v3"
    idioma="pt",
    formato="srt",
)

# Estruturação local com Ollama
labdados.estruturacao(
    arquivos="textos/",
    schema={"type": "object", "properties": {"resumo": {"type": "string"}}},
    local=True,
    modelo_local="qwen2.5:7b",
)

# Estruturação local com OpenAI direto
labdados.estruturacao(
    arquivos="textos/",
    schema={...},
    local=True,
    base_url_local="https://api.openai.com/v1",
    api_key_local="sk-...",
    modelo_local="gpt-4o-mini",
)

# Viabilidade (sempre local, sem nuvem por enquanto)
labdados.analise_viabilidade(
    descricao="Sentenças TJSP sobre direito do consumidor.",
    listagem="datajud",
    tribunais=["tjsp"],
    classes_cnj="436",
    inicio="2024-01-01",
    fim="2024-06-30",
    saida="viab/",
)
```

---

## Modo 3 — Backend local via Docker

Use quando você quer **rodar todo o escritório no seu computador** — útil para:

- Desenvolver / testar mudanças no backend sem mexer em prod.
- Debugar o fluxo end-to-end (upload → fila → service → download).
- Demos sem depender de internet ou da cota da nuvem.

A receita: subir o repositório [`escritorio-servicos`](https://github.com/labdados/escritorio-servicos) via `docker compose`, criar uma API key local, e apontar o SDK para `http://localhost:18000` (ou 8000 se a porta padrão estiver livre).

### 1. Subir o stack

```bash
git clone https://github.com/labdados/escritorio-servicos
cd escritorio-servicos
cp .env.example .env       # defaults funcionam
docker compose --profile services up -d
```

Se a porta 8000 já estiver em uso por outro projeto, use o override que mapeia para portas alternativas:

```bash
docker compose -f docker-compose.yml -f .dev-notes/docker-compose.alt-ports.yml --profile services up -d
# backend: http://localhost:18000   (em vez de 8000)
# frontend: http://localhost:13000  (em vez de 3000)
```

### 2. Criar uma API key local

Em dev local não tem o fluxo de aprovação por e-mail — você cria a key direto no Postgres:

```bash
docker exec -i labdados-postgres psql -U labdados -d labdados <<'SQL'
INSERT INTO api_keys (id, key_hash, key_prefix, email, researcher_name, institution, status, monthly_budget_brl, created_at)
VALUES (
    gen_random_uuid()::text,
    encode(sha256('sk_lab_dev_token_secreto'::bytea), 'hex'),
    'sk_lab_dev',
    'dev@local',
    'Dev Local',
    'Local',
    'ACTIVE',
    1000.0,
    NOW()
);
SQL
```

Plaintext da key: `sk_lab_dev_token_secreto` (escolha o seu).

### 3. Apontar o SDK

```python
import os
os.environ["LABDADOS_BASE_URL"] = "http://localhost:18000"  # ou 8000

import labdados
labdados.ocr(
    arquivos="pdfs/",
    api_key="sk_lab_dev_token_secreto",
    saida="out/",
)
```

Ou, equivalente sem variável de ambiente:

```python
client = labdados.Client(
    api_key="sk_lab_dev_token_secreto",
    base_url="http://localhost:18000",
)
client.ocr(arquivos="pdfs/", saida="out/")
```

### O que vem por default no Docker

- **OCR**: build CPU (`pymupdf-tesseract`). Para `paddleocr` (GPU), use o override `docker-compose.gpu.yml`.
- **Transcrição**: build CPU (faster-whisper standalone). `model_id="whisperx"` retorna 400 com mensagem clara — para WhisperX + diarização, use `docker-compose.gpu.yml`.
- **Estruturação**: usa Azure OpenAI (`gpt-4.1-mini`). Configure `AZURE_OPENAI_ENDPOINT` e `AZURE_OPENAI_KEY` no `.env` antes de subir.
- **Viabilidade**: funciona out-of-the-box.

### Subindo com GPU local

Se você tem NVIDIA GPU + [NVIDIA Container Toolkit](https://github.com/NVIDIA/nvidia-container-toolkit):

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile services up -d
```

O override troca os builds de OCR e Transcrição para os Dockerfiles GPU (PaddleOCR + WhisperX + pyannote).

---

## Documentação completa

- [API reference (quartodoc)](https://labdados.github.io/labdados-sdk)
- [Exemplos práticos por serviço](docs/exemplos/)
- [Como pedir uma API key](https://labdados-frontend.livelydesert-3e3e3dd8.brazilsouth.azurecontainerapps.io/consultoria/api-key)

## Como manter sincronizado com o backend

Este pacote é **espelho da API v1** do escritório
(`https://github.com/labdados/escritorio-servicos`). A maior parte da
lógica compartilhada vive no [`labdados-core`](https://github.com/lab-dados/labdados-core),
que é dependência transitiva (puxado pelos extras). O guia para agentes
de IA e mantenedores está no [`CLAUDE.md`](./CLAUDE.md).

## Licença

[MIT](./LICENSE)
