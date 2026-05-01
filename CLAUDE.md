# CLAUDE.md — `labdados-sdk`

Guia para agentes de IA (Claude Code) e mantenedores que vão modificar este
pacote. Este é o SDK Python oficial dos serviços do **escritório de apoio do
LabDados** (FGV Direito SP).

## Arquitetura geral (3 repos)

```
labdados-core/                       núcleo Python
   │  └─ viabilidade/               regras + render do relatório
   │  └─ templates/                 Jinja .qmd embutido no wheel
   │
   ├──→ escritorio-servicos/        backend FastAPI + workers
   │     viability_runner.py        thin wrapper (estado em DB + blob)
   │
   └──→ labdados-sdk/               este repo — cliente nuvem + facade local
         analise_viabilidade.py     thin wrapper (modo nuvem chama API,
                                    modo local importa labdados_core)
```

A regra: **sem dep circular**. Backend e SDK são folhas; ambos puxam
`labdados-core`. Lógica que precisa ficar idêntica nos dois → vai pro core.
Lógica específica de um → fica nele.

Ver também:
- [`escritorio-servicos/CLAUDE.md`](https://github.com/jtrecenti/escritorio-servicos/blob/main/CLAUDE.md)
- [`labdados-core/CLAUDE.md`](https://github.com/lab-dados/labdados-core/blob/main/CLAUDE.md)

## O que este pacote é (e o que **não** é)

- **É** o cliente Python oficial dos endpoints `/api/v1/*` do backend em
  [`escritorio-servicos`](../escritorio-servicos). A superfície pública do
  SDK precisa estar **sempre alinhada** com a API exposta nessa rota.
- **É** uma camada uniforme que oferece dois modos:
  - `cloud` (default): chama a API REST do escritório com `X-API-Key`.
  - `local` (`local=True`): processa no próprio computador, usando
    extras opcionais do `pyproject.toml`.
- **Não é** um framework genérico de NLP/jurimetria. Cada função aqui
  corresponde 1:1 a um serviço do escritório, e nada mais.

## Layout

```
labdados-sdk/
├── pyproject.toml                     # extras: ocr, transcricao, estruturacao, viabilidade
├── src/labdados/
│   ├── __init__.py                    # re-exports + docstring do pacote
│   ├── _version.py
│   ├── _io.py                         # resolve pasta / lista / arquivo único
│   ├── _progress.py                   # spinner sem deps (sys.stderr)
│   ├── client.py                      # Client + helpers HTTP / upload / polling
│   ├── exceptions.py
│   ├── ocr.py
│   ├── transcricao.py
│   ├── estruturacao.py
│   └── analise_viabilidade.py
├── tests/test_smoke.py                # imports + fluxo nuvem mockado via respx
├── docs/                              # quartodoc → site estático
│   ├── _quarto.yml
│   ├── index.qmd
│   ├── getting-started.qmd
│   └── exemplos/
└── examples/                          # scripts .py rodáveis (cópia do que está nos .qmd)
```

## Princípio de design

> **Uma pessoa que sabe Python só o suficiente para abrir um notebook precisa
> conseguir usar o SDK em 3 linhas.**

Tudo em português (parâmetros, mensagens de erro, docstrings — exceto os
nomes técnicos como `api_key`, `Client`, `schema`, `temperatura`). Uma única
chamada faz tudo: resolve inputs, sobe arquivos, dispara o job, faz polling,
baixa o resultado. Sem callbacks, sem async — é tudo síncrono.

## Como **manter sincronizado com o backend**

O backend pode mudar sem aviso. Antes de qualquer release deste pacote:

1. **Releia `backend/app/routers/v1.py`** no monorepo `escritorio-servicos`
   — todo endpoint que o SDK chama mora ali. Compare com `client.py` e os
   módulos de serviço.
2. **Releia `backend/app/services_catalog.py`**: os IDs de serviço/modelo
   e os campos de `config` viram literais no SDK (ex.: `"pymupdf-tesseract"`,
   `output_format`). Quando aparecer um modelo novo ou um campo de config
   novo, exponha-o aqui como argumento nomeado da função correspondente.
3. **Releia `backend/app/schemas.py`**:
   - `SdkRequestCreate` define o payload de `POST /api/v1/requests`.
   - `SdkViabilityCreate` define o de `POST /api/v1/viability`.
   - `FileMetadata` define o formato esperado em `files_metadata`.
4. **Releia `services/<svc>/`** se houver mudança no contrato do serviço
   downstream — embora o backend faça o adaptador, novos campos de config
   acabam vindo até aqui.

### Checklist de release

- [ ] `pytest -q` passa (smoke tests com `respx`).
- [ ] `ruff check .` limpo.
- [ ] Bumpou `_version.py` e o changelog.
- [ ] Documentação atualizada — `cd docs && quarto render`.
- [ ] Exemplos em `examples/` foram **executados** uma vez contra a API
      real (com uma API key de teste) e os outputs conferem.

## Modo local

Cada serviço tem um caminho `_*_local(...)` independente do remoto. Manter:

- **OCR**: PyMuPDF (PDF → imagem) + Tesseract (imagem → texto). Tesseract
  é binário do sistema (não Python) — a mensagem de erro fala disso.
- **Transcrição**: `faster-whisper` em CPU/GPU. **Diarização local não é
  suportada** (pyannote tem deps pesadas e licença HF) — se o usuário pedir
  com `local=True`, falhamos cedo OU ignoramos com warning. Hoje ignoramos
  silenciosamente; revisitar se virar reclamação.
- **Estruturação**: cliente OpenAI-compat. Defaults apontam pra Ollama em
  `localhost:11434/v1` (ele é gratuito, simples e cobre a maioria dos casos
  de notebook). Aceita Azure OpenAI / OpenAI / vLLM se o usuário trocar
  `base_url_local` e `api_key_local`.
- **Viabilidade**: usa `labdados_core.viabilidade` direto. **Não duplique**
  a lógica de `analyze_form` aqui — se precisar mudar a regra, mude no
  `labdados-core` e bumpe a versão.

## Documentação

`quartodoc` lê os docstrings (estilo NumPy/Google) e gera o site em `docs/_site`.
A configuração está em `docs/_quarto.yml`. Para regerar:

```bash
cd docs
quartodoc build       # extrai docs/api/*.qmd a partir dos docstrings
quarto render
quarto preview        # opcional, navegador local
```

Os exemplos em `docs/exemplos/*.qmd` precisam ser **rodáveis** (`eval: false`
quando precisarem de internet ou binários — mas o código deve ser correto).

## Boas práticas para mexer no SDK

1. **Não introduza dependências obrigatórias além de `httpx`**. Tudo o mais
   é extra. O usuário típico instala `pip install labdados` num notebook e
   começa a chamar funções de nuvem na hora.
2. **Erros HTTP viram exceções específicas** (`ApiKeyError` em 401/403,
   `ProcessingFailed` em FAILED, `LabdadosError` no resto). Não vaze
   `httpx.HTTPError` cru.
3. **Polling é a única coisa "lenta" do SDK** — sempre exponha
   `progress: bool` para silenciar.
4. **Ao adicionar um novo parâmetro**: prefira nome em português; quando
   o backend espera inglês, faça a tradução no `config` (ex.: usuário passa
   `idiomas="por+eng"`, mandamos `{"languages": "por+eng"}`).
5. **Modo local nunca chama a API** — não deve ser um fallback automático
   nem misturar os dois. O usuário escolhe um dos dois explicitamente.

## Quem é o público

- **Pesquisadores** (mestrandos, doutorandos, alunos de IC) com Python básico.
- **Equipe LabDados** rodando coletas em larga escala em scripts.
- O **backend do escritório NÃO usa o SDK** (evita dep circular). Lógica
  compartilhada vai pra ``labdados-core``, consumida pela ``services/viability/``
  no monorepo e pelo ``_viab_local`` aqui no SDK.
