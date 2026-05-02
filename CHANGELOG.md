# Changelog

Todas as mudanças notáveis neste pacote são documentadas aqui.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
versionamento seguindo [SemVer](https://semver.org/lang/pt-BR/).

## [Unreleased]

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
