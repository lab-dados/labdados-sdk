# labdados — SDK Python

SDK oficial dos serviços do **escritório de apoio do LabDados** (FGV Direito SP).

Quatro funções de alto nível, em português, que cobrem os serviços do escritório:

- `labdados.ocr(...)` — OCR de PDFs (texto e markdown).
- `labdados.transcricao(...)` — transcrição (Whisper) e diarização de áudio.
- `labdados.estruturacao(...)` — extração estruturada de campos com LLMs.
- `labdados.analise_viabilidade(...)` — estima volume de processos antes de uma raspagem.

Cada função roda em **dois modos**:

1. **Nuvem** (default) — processa na infra do escritório. Exige uma API key (peça em <https://labdados-frontend.livelydesert-3e3e3dd8.brazilsouth.azurecontainerapps.io/consultoria/api-key>).
2. **Local** (`local=True`) — processa no próprio computador. Cada serviço tem extras opcionais (`pip install labdados[ocr]`, `[transcricao]`, `[estruturacao]`, `[viabilidade]`).

## Instalação

```bash
pip install labdados                    # base (apenas modo nuvem)
pip install labdados[ocr]               # + Tesseract local
pip install labdados[transcricao]       # + faster-whisper
pip install labdados[estruturacao]      # + cliente OpenAI (Ollama, Azure OpenAI, OpenAI, ...)
pip install labdados[viabilidade]       # + juscraper + jinja2
pip install labdados[all]               # tudo
```

## Uso mínimo

```python
import labdados

# Modo nuvem (precisa de API key)
labdados.ocr(
    arquivos="meus_pdfs/",
    api_key="sk_lab_...",
    saida="resultados/",
)

# Modo local
labdados.ocr(
    arquivos=["a.pdf", "b.pdf"],
    local=True,
    saida="resultados/",
)
```

## Cliente reutilizável

```python
client = labdados.Client(api_key="sk_lab_...")
client.ocr(arquivos="pdfs/", saida="out_pdf/")
client.transcricao(arquivos="audios/", saida="out_audio/", modelo="whisperx", diarizacao=True)
```

## Documentação

- [Documentação completa (quartodoc)](https://labdados.github.io/labdados-sdk)
- [Exemplos práticos por serviço](docs/exemplos/)
- [Como pedir uma API key](https://labdados-frontend.livelydesert-3e3e3dd8.brazilsouth.azurecontainerapps.io/consultoria/api-key)

## Como manter sincronizado com o backend

Este pacote é **espelho da API v1** do escritório
(`https://github.com/labdados/escritorio-servicos`). Cada vez que a API muda
(novos modelos, novos parâmetros de configuração, novos serviços), o SDK
precisa ser atualizado em sintonia. O guia para agentes de IA e mantenedores
está no [`CLAUDE.md`](./CLAUDE.md).

## Licença

[MIT](./LICENSE)
