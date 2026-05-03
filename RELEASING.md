# Releasing `labdados`

Procedimento para publicar uma nova versão do SDK no PyPI.

## Pré-requisitos (uma vez só)

1. **Trusted Publisher no PyPI**:
   - Acesse <https://pypi.org/manage/account/publishing/> logado como mantenedor.
   - "Add a new pending publisher":
     - PyPI Project Name: `labdados`
     - Owner: `lab-dados`
     - Repository: `labdados-sdk`
     - Workflow filename: `release.yml`
     - Environment name: `pypi`
2. **GitHub Environment**: `Settings → Environments → New environment` chamado `pypi`.
3. **`labdados-core>=0.9` no PyPI**: enquanto o core estiver com
   `juscraper @ git+...`, o SDK também não publica (porque seus extras puxam
   `labdados-core @ git+...` — direct ref proibido em metadata). Sequência
   correta:
   1. Cortar `juscraper v0.3.0` no PyPI (jtrecenti/juscraper).
   2. Cortar `labdados-core` no PyPI (depende de juscraper>=0.3).
   3. Cortar `labdados` aqui (depende de labdados-core>=0.9 nos extras).

## Release

1. Trocar as deps em `[project.optional-dependencies]`:
   ```diff
   - "labdados-core[ocr-cpu] @ git+https://github.com/lab-dados/labdados-core@main",
   + "labdados-core[ocr-cpu]>=0.9,<1.0",
   ```
   Aplicar nas 4 entries (`ocr`, `transcricao`, `estruturacao`, `viabilidade`).
   Pode-se remover `[tool.hatch.metadata] allow-direct-references = true`
   depois.
2. Bump em `src/labdados/_version.py` e duplicar em `pyproject.toml`
   (`version = ...`).
3. Mover `[Unreleased]` → `[X.Y.Z] - YYYY-MM-DD` no `CHANGELOG.md`.
4. `uv run pytest -q` deve passar (smoke tests com `respx`).
5. **Antes de tagar**: rode os notebooks em `examples/notebooks/` contra a
   API real ao menos uma vez (cada um). O Colab badge precisa abrir e
   rodar — é a primeira impressão do pacote.
6. Commit + tag:
   ```bash
   git commit -am "release: vX.Y.Z"
   git tag vX.Y.Z
   git push origin main vX.Y.Z
   ```
7. Workflow `release.yml` builda e publica via OIDC. Ver em
   <https://github.com/lab-dados/labdados-sdk/actions>.

## Smoke test pós-release

```bash
pip install labdados==X.Y.Z
python -c "import labdados; print(labdados.__version__)"
# Modo nuvem mínimo
python -c "import labdados; labdados.Client(api_key='sk_lab_TEST').test_connection()"
```

## Em caso de problema

- PyPI **não permite** apagar versão — só `yank`. Lance patch.
- Para testar antes: ative TestPyPI no workflow temporariamente.
