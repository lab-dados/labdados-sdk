"""Exceções do SDK ``labdados``."""


class LabdadosError(Exception):
    """Erro genérico do SDK."""


class ApiKeyError(LabdadosError):
    """API key ausente, inválida ou revogada."""


class UploadError(LabdadosError):
    """Falha no upload de arquivo para o storage."""


class ProcessingFailed(LabdadosError):
    """O serviço retornou ``status=FAILED``.

    O atributo ``request_id`` aponta o pedido no escritório (use no suporte).
    """

    def __init__(self, message: str, request_id: str | None = None) -> None:
        super().__init__(message)
        self.request_id = request_id


class LocalDependencyMissing(LabdadosError):
    """Algum extra opcional não está instalado para o modo local.

    Mensagem inclui o ``pip install labdados[<extra>]`` correto.
    """
