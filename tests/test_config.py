import pytest

from invoices.config import ConfigError, load_config

MINIMAL = """
data:
  out: data/invoices.jsonl
models:
  small: {}
  large: {}
"""


def write(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_paths_resolve_relative_to_config(tmp_path):
    cfg = load_config(write(tmp_path, MINIMAL), env={})
    assert cfg.data.out == (tmp_path / "data/invoices.jsonl").resolve()
    assert cfg.eval.dataset == (tmp_path / "data/invoices.jsonl").resolve()
    assert cfg.pipeline.max_retries == 2


def test_env_overrides_model_names(tmp_path):
    cfg = load_config(
        write(tmp_path, MINIMAL),
        env={"LLM_API_BASE": "http://localhost:8000/v1", "LLM_API_KEY": "k",
             "LLM_MODEL_SMALL": "s", "LLM_MODEL_LARGE": "l"},
    )
    assert cfg.model("small").model == "s"
    assert cfg.model("large").model == "l"
    assert cfg.llm.api_key == "k"


def test_models_unconfigured_by_default(tmp_path):
    cfg = load_config(write(tmp_path, MINIMAL), env={})
    assert cfg.model("small").configured is False


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "absent.yaml", env={})


def test_unknown_model_key(tmp_path):
    cfg = load_config(write(tmp_path, MINIMAL), env={})
    with pytest.raises(ConfigError):
        cfg.model("medium")


@pytest.mark.parametrize(
    "text",
    [
        "data:\n  count: 0\n",
        "data:\n  typo_probability: 1.5\n",
        "pipeline:\n  max_retries: -1\n",
        "models:\n  small:\n    max_output_tokens: 0\n",
        "models:\n  small:\n    price_per_1m_input: -2\n",
        "models:\n  small:\n    unknown_key: 1\n",
        "eval:\n  models: [medium]\n",
        "eval:\n  name_edit_distance: -1\n",
        "llm:\n  timeout_s: 0\n",
    ],
)
def test_invalid_configs(tmp_path, text):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, text), env={})
