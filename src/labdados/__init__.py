"""
labdados — SDK Python para os serviços do escritório de apoio do
LabDados (FGV Direito SP).

Quatro funções de alto nível, cada uma cobre um serviço do escritório e
funciona em dois modos:

- **Nuvem** (default): processa via API do escritório, exige `api_key`.
- **Local** (`local=True`): processa no próprio computador, exige extras
  opcionais instalados (ex.: `pip install labdados[ocr]`).

Uso mínimo (modo nuvem):

    >>> import labdados
    >>> labdados.ocr(arquivos="meus_pdfs/", api_key="sk_lab_...", saida="resultados/")

Modo local:

    >>> import labdados
    >>> labdados.ocr(arquivos="meus_pdfs/", local=True, saida="resultados/")

Para uso em scripts mais elaborados (várias chamadas com a mesma chave),
prefira o `Client`:

    >>> client = labdados.Client(api_key="sk_lab_...")
    >>> client.ocr(arquivos="pdfs/", saida="out/")
    >>> client.transcricao(arquivos="audios/", saida="out_audios/")
"""

from labdados._version import __version__
from labdados.analise_viabilidade import analise_viabilidade
from labdados.anonimizacao import anonimizacao
from labdados.client import Client
from labdados.estruturacao import estruturacao
from labdados.exceptions import (
    ApiKeyError,
    LabdadosError,
    LocalDependencyMissing,
    ProcessingFailed,
    UploadError,
)
from labdados.ocr import ocr
from labdados.transcricao import transcricao

__all__ = [
    "__version__",
    "Client",
    # Funções de alto nível
    "ocr",
    "transcricao",
    "estruturacao",
    "anonimizacao",
    "analise_viabilidade",
    # Exceções
    "LabdadosError",
    "ApiKeyError",
    "UploadError",
    "ProcessingFailed",
    "LocalDependencyMissing",
]
