# Contributing to POLARIS

Thanks for helping improve POLARIS. The project is designed to stay offline-first, deterministic for scoring, and easy to extend with new frameworks.

## Development Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
pytest
```

On macOS or Linux, activate with `source .venv/bin/activate`.

## Adding a Framework

Add a JSON file under `data/frameworks/` using this schema:

```json
{
  "framework": "FRAMEWORK_NAME",
  "version": "1.0",
  "controls": [
    {
      "id": "CTRL-1",
      "function": "GOVERN",
      "name": "Control Name",
      "description": "What this control expects.",
      "required_clauses": ["required clause one", "required clause two"]
    }
  ]
}
```

Then register the file in `FRAMEWORKS` inside `main.py` if you want it available by short name.

## Testing

Run the full test suite:

```bash
pytest --cov=engine --cov=output --cov-report=term-missing
```

Tests should avoid internet access and should not require Ollama. Semantic detection tests can inject a local test embedding model.

## Pull Request Expectations

- Keep gap detection and scoring deterministic.
- Do not add external API calls to analysis paths.
- Include tests for new ingestion, scoring, framework, or report behavior.
- Update README and CHANGELOG for user-facing changes.
