# Changelog

Todas as mudanças notáveis neste pacote são documentadas aqui.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
versionamento seguindo [SemVer](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Corrigido
- Upload recusa arquivo vazio com `UploadError` claro. Antes, um download
  que falhava no Colab (`wget -O` cria o arquivo mesmo com 403) subia 0 byte
  e a transcrição quebrava no servidor com erro obscuro do `ffprobe`.
- Notebooks baixam os arquivos de exemplo com User-Agent identificado e
  checagem de tamanho; o áudio de exemplo passou a ser o trecho em domínio
  público do discurso de posse de J. F. Kennedy (`jfk.flac`, no GitHub do
  Whisper), em vez do Wikimedia, que bloqueia downloads vindos do Colab.

### Adicionado
- Notebook `examples/notebooks/nuvem_todos_os_modelos.ipynb` (com badge
  "Open in Colab") que roda todos os serviços com API key variando os
  modelos de nuvem: OCR (2), transcrição, estruturação (9), anonimização (2),
  embeddings (4) e o `Client`.
- `Client.solicitacoes(limite=50)` — lista as solicitações feitas com a chave.
- Atalhos `Client.anonimizacao(...)` e `Client.embeddings(...)`.

### Documentação
- Site: páginas "Embeddings" e "Todos os modelos na nuvem"; exemplos de OCR,
  transcrição e estruturação atualizados para os modelos do Azure AI Foundry;
  `anonimizacao` e `embeddings` na referência da API.

## [0.11.0] - 2026-10-01

### Adicionado
- `labdados.embeddings(...)` — transforma textos (`.txt/.md/.docx/.csv/.xlsx`)
  em vetores. Nuvem: `text-embedding-3-small` (default),
  `text-embedding-3-large`, `embed-v-4-0`, `Cohere-embed-v3-multilingual`.
  Local: sentence-transformers (`pip install labdados[embeddings-local]`) ou
  qualquer servidor OpenAI-compatível via `base_url_local`. Saída
  `embeddings.parquet` + `chunks.csv`; `dataframe=True` devolve um DataFrame.
- OCR na nuvem: `modelo="azure-document-intelligence"` e `"mistral-ocr"`.
- Transcrição na nuvem: `modelo="azure-speech"` (com diarização).
- Estruturação na nuvem: `gpt-4.1`, `gpt-5-mini`, `gpt-5.6-terra`,
  `gpt-6-luna`, `DeepSeek-V4-Flash`, `Mistral-Large-3`, `Kimi-K2.6`.

### Alterado
- **Default de modelo na nuvem**: `ocr()` usa `azure-document-intelligence`
  e `transcricao()` usa `azure-speech` (antes `pymupdf-tesseract` e
  `whisper-large-v3-turbo`). Os modelos antigos continuam aceitos enquanto
  os servidores GPU do escritório não forem desligados; o modo local não muda.

## [0.10.0] - 2026-10-01

### Adicionado
- `labdados.estruturacao(modelo="gpt-5.6-luna")` — modelo de raciocínio
  servido pelo recurso Azure OpenAI da FGV (Brazil South, Global
  Standard). Mais capaz em textos longos/difíceis; mais caro e ignora
  `temperatura`. O default continua `gpt-4.1-mini`, agora também servido
  pelo recurso da FGV.
- Modo local reconhece endpoints Azure (`*.openai.azure.com`,
  `*.services.ai.azure.com`) e os chama pela API v1 OpenAI-compatível —
  dá para usar direto a chave do recurso da FGV com
  `base_url_local=<endpoint>`, `modelo_local=<deployment>`.
- `temperatura=None` omite o parâmetro (obrigatório no modo local com
  modelos de raciocínio).

### Alterado
- Extra `[estruturacao]` exige `labdados-core>=0.12`.

## [0.9.0] - 2026-08-24

### Adicionado
- Parâmetro `text=True` em `labdados.ocr(...)` e `labdados.transcricao(...)`:
  devolve o texto como `str` em vez do caminho da pasta. Os arquivos
  continuam sendo gravados em `saida`. Funciona nos dois modos: no local
  lê os `.txt`/`.md`/`.srt` gerados, e na nuvem lê de dentro do `.zip`
  baixado, sem exigir que quem chama saiba desses detalhes.
- Helper interno `labdados._io.collect_text(paths)`, compartilhado pelos
  dois serviços.
- Modelo `tiny` da transcrição local passa a vir das releases deste
  repositório, e não do Hugging Face. O HF barra download anônimo vindo de
  IP de datacenter (Google Colab, runners de CI) pedindo um `HF_TOKEN`, o
  que quebrava o modo `local=True` justamente para quem não quer instalar
  nada. O modelo fica em cache em `~/.cache/labdados/modelos/`.
- `modelo_local` aceita o caminho de uma pasta com o modelo já baixado.
- Variável de ambiente `LABDADOS_CACHE` para escolher onde os modelos
  espelhados ficam, e `LABDADOS_MODELOS_HF=1` para forçar o Hugging Face.
- Módulo interno `labdados._modelos`, com download atômico (baixa e extrai
  em caminho temporário, só então move) para que uma interrupção não deixe
  cache pela metade.

## [0.8.0] - 2026-05-04

### Adicionado
- Função `labdados.anonimizacao(...)` — detecção e mascaramento de PII
  em texto. Modo nuvem roteia para o serviço novo do escritório
  (`/api/v1/requests` com `service_id="anonimizacao"`); modo local
  delega ao `labdados_core.anonimizacao` (HF Transformers).
  Aceita `.txt`, `.md`, `.docx`, `.csv` e `.xlsx`.
- Dois modelos disponíveis em modo nuvem (e idem no local, com o HF
  identifier mapeado automaticamente):
  - `"privacy-filter"` (default) — multilíngue, 8 categorias PII
    (`openai/privacy-filter`).
  - `"lenerbr"` — PT-BR jurídico, 6 categorias incluindo
    `LEGISLACAO`/`JURISPRUDENCIA`
    (`pierreguillou/ner-bert-base-cased-pt-lenerbr`).
- Estratégias de mascaramento: `"categoria"` (default — `[PESSOA]`,
  `[EMAIL]`...), `"asteriscos"` (preserva tamanho) e `"pseudonimo"`
  (`PESSOA_1`, `PESSOA_2`... consistente por documento).
- Novo extra `pip install labdados[anonimizacao]` — puxa
  `labdados-core[anonimizacao-cpu]>=0.11,<1.0`.

### Mudado
- Pin do `labdados-core` no extra de anonimização exige `>=0.11`
  (versão que adiciona suporte ao LeNER-Br).

## [0.7.2] - 2026-05-03

### Mudado
- Notebooks Colab refatorados para que **cada célula de código seja
  auto-suficiente** (`import labdados` + auth via `getpass` no início de
  toda célula que executa) — alguém pode rodar só a célula do modo nuvem
  ou só a do modo local sem precisar rodar tudo na ordem.
- Trocou exemplos de `gpt-4o-mini` por `gpt-4.1-mini` em README, docs e
  notebooks (4o-mini está obsoleto).
- URL do portal de API key passou a apontar para a URL real do escritório
  (`labdados-frontend.…brazilsouth.azurecontainerapps.io/consultoria/api-key`)
  em vez do domínio `labdados.fgv.br` (ainda não configurado).

### Removido
- `examples/data/organograma.pdf` — fixture interna que não deveria ter
  ido pro repo público. Notebook de OCR agora baixa um paper público
  hospedado pelo Mozilla pdf.js (TraceMonkey, ~14 páginas) via `wget`.
  Histórico purgado com `git filter-repo` (junto com `data/audio…m4a`).

## [0.7.1] - 2026-05-03

### Mudado
- **Primeira release no PyPI.** Trocou os 4 `labdados-core @ git+...`
  em `[project.optional-dependencies]` por `labdados-core[…]>=0.9,<1.0`
  (labdados-core 0.9.1 publicado hoje no PyPI).
- Removeu `[tool.hatch.metadata] allow-direct-references = true`.

### Adicionado
- `examples/notebooks/{ocr,transcricao,estruturacao,analise_viabilidade}.ipynb` —
  versões em notebook dos exemplos da documentação, com badge "Open in Colab"
  no topo. Cada um é auto-suficiente: instala o pacote, autentica via
  `getpass`, baixa/gera dados de amostra e roda.
- Badges "Open in Colab" no topo de cada `docs/exemplos/*.qmd`, apontando
  para o notebook correspondente no GitHub.
- `examples/data/organograma.pdf` — fixture pequeno usado pelo notebook
  de OCR.
- `RELEASING.md` com procedimento de release via Trusted Publisher.
- `.github/workflows/release.yml` — publica em PyPI via OIDC quando uma
  tag `v*` é empurrada.

### Corrigido
- URLs do `pyproject.toml`, `_quarto.yml` e `README.md` que apontavam para
  `github.com/labdados/...` (org não existente) — agora usam
  `lab-dados` (org real, com hífen).

## [0.7.0] - 2026-05-02

### Mudado
- `transcricao` modo local: helpers de timestamp (`_fmt_timestamp`,
  `_fmt_srt`) e o loop de escrita SRT/VTT/TXT vieram pra cá do
  `labdados_core.transcricao`. Mesma rotina rodada pelo serviço no
  escritório.
- **Compatível** com chamadas existentes — única diferença é que os
  timestamps SRT agora incluem milissegundos (eram truncados em
  segundos).

### Adicionado
- Dep transitiva `labdados-core` no extra `[transcricao]` (já vinha
  no `[estruturacao]` desde a v0.5.0 e em `[ocr]` desde a v0.6.0).

## [0.6.0] - 2026-05-02

### Mudado
- `ocr` modo local: pipeline (PyMuPDF + Tesseract + deskew + BW
  fallback + descoberta automática do binário Tesseract no Windows)
  veio pra `labdados_core.ocr.extract`. Mesmo pipeline rodado pelo
  serviço no escritório.
- Extra `[ocr]` agora puxa `labdados-core[ocr-cpu]` em vez de
  duplicar PyMuPDF/pytesseract/Pillow.
- BW fallback (re-OCR em PB binário quando Tesseract devolve vazio)
  agora vale para o SDK também — antes era só do backend.

## [0.5.0] - 2026-05-02

### Mudado (breaking — leve)
- `requires-python` apertado de `>=3.10` para `>=3.11` (alinhado com
  `labdados-core`, que usa `typing.NotRequired` e `enum.StrEnum`).
- `estruturacao` modo local: pipeline (cliente OpenAI-compat,
  prompts, leitura de `.txt/.md/.docx/.csv/.xlsx`) veio pra
  `labdados_core.estruturacao`. Mesma rotina rodada pelo serviço.
- **Mudança de comportamento**: schema agora é injetado na mensagem
  `user` (junto do texto), não mais na `system`. Alinha com o backend
  e funciona melhor com `response_format=json_schema`. Se o seu
  prompt depender da formulação antiga, instrua o LLM via
  `prompt_sistema` ou abra uma issue.

### Adicionado
- Extra `[estruturacao]` passa a puxar
  `labdados-core[estruturacao]` em vez de `openai>=1.40` direto
  (DataFrameIt + dependências vêm transitivamente).

## [0.4.0] - 2026-04

### Mudado
- `analise_viabilidade` virou **só local** (`local=True` implícito).
  A nuvem não tem mais endpoint `/api/v1/viability` separado — toda
  a lógica vive em `labdados_core.viabilidade`.
- `estruturacao` reduzido para um único modelo nuvem
  (`gpt-4.1-mini`); modelos vLLM self-hosted (`gpt-oss-20b`,
  `gemma-4-26b-it`) foram descontinuados por custo.

### Adicionado
- Documentação de cota mensal (R$ 50/mês default por API key).

## Notas de versão anteriores

A versão 0.3.0 e anteriores não têm changelog estruturado — consulte
o histórico do git.
