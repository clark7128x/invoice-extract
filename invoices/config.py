from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Mapping

import yaml


class ConfigError(ValueError):
    pass


def _need(cond: bool, msg: str) -> None:
    if not cond:
        raise ConfigError(msg)


def _build(cls, data: dict, section: str):
    known = {f.name for f in fields(cls)}
    unknown = set(data) - known
    _need(not unknown, f"{section}: невідомі ключі {sorted(unknown)}")
    try:
        return cls(**data)
    except TypeError as exc:
        raise ConfigError(f"{section}: {exc}") from exc


@dataclass(frozen=True)
class DataConfig:
    out: Path
    count: int = 150
    seed: int = 17
    vat_absent_probability: float = 0.35
    typo_probability: float = 0.06

    def __post_init__(self) -> None:
        _need(self.count > 0, "data.count має бути > 0")
        for name in ("vat_absent_probability", "typo_probability"):
            value = getattr(self, name)
            _need(0 <= value <= 1, f"data.{name} має бути в [0, 1]")


@dataclass(frozen=True)
class LLMConfig:
    base_url: str = ""
    api_key: str | None = None
    timeout_s: float = 60.0
    max_retries: int = 3
    retry_base_delay_s: float = 1.0
    retry_max_delay_s: float = 20.0

    def __post_init__(self) -> None:
        _need(self.timeout_s > 0, "llm.timeout_s має бути > 0")
        _need(self.max_retries >= 0, "llm.max_retries має бути >= 0")
        _need(self.retry_base_delay_s >= 0, "llm.retry_base_delay_s має бути >= 0")
        _need(self.retry_max_delay_s >= 0, "llm.retry_max_delay_s має бути >= 0")


@dataclass(frozen=True)
class ModelConfig:
    key: str
    model: str | None = None
    temperature: float = 0.0
    max_output_tokens: int = 1200
    json_mode: bool = False
    price_per_1m_input: float | None = None
    price_per_1m_output: float | None = None

    def __post_init__(self) -> None:
        _need(self.temperature >= 0, f"models.{self.key}.temperature має бути >= 0")
        _need(self.max_output_tokens > 0, f"models.{self.key}.max_output_tokens має бути > 0")
        for name in ("price_per_1m_input", "price_per_1m_output"):
            value = getattr(self, name)
            _need(value is None or value >= 0, f"models.{self.key}.{name} має бути >= 0 або null")

    @property
    def configured(self) -> bool:
        return bool(self.model)


@dataclass(frozen=True)
class PipelineConfig:
    max_retries: int = 2
    max_input_chars: int = 8000

    def __post_init__(self) -> None:
        _need(self.max_retries >= 0, "pipeline.max_retries має бути >= 0")
        _need(self.max_input_chars > 0, "pipeline.max_input_chars має бути > 0")


@dataclass(frozen=True)
class EvalConfig:
    dataset: Path
    models: tuple[str, ...] = ("small", "large")
    results_dir: Path = Path("results")
    call_log: Path = Path("results/calls.jsonl")
    amount_tolerance: float = 0.01
    name_edit_distance: int = 1

    def __post_init__(self) -> None:
        _need(self.amount_tolerance >= 0, "eval.amount_tolerance має бути >= 0")
        _need(self.name_edit_distance >= 0, "eval.name_edit_distance має бути >= 0")
        _need(bool(self.models), "eval.models не може бути порожнім")


@dataclass(frozen=True)
class Config:
    data: DataConfig
    llm: LLMConfig
    models: dict[str, ModelConfig]
    pipeline: PipelineConfig
    eval: EvalConfig
    raw: dict[str, Any]

    def model(self, key: str) -> ModelConfig:
        if key not in self.models:
            raise ConfigError(f"Невідома модель: {key}. Доступні: {sorted(self.models)}")
        return self.models[key]


def load_config(path: str | Path | None = None, env: Mapping[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    cfg_path = Path(path or env.get("INV_CONFIG") or "config.yaml")
    if not cfg_path.is_file():
        raise ConfigError(f"Немає конфігу: {cfg_path}")
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    _need(isinstance(raw, dict), "config.yaml має містити словник")
    base = cfg_path.resolve().parent

    def resolve(value: str | Path) -> Path:
        return (base / value).resolve()

    data_raw = dict(raw.get("data") or {})
    data = _build(
        DataConfig, data_raw | {"out": resolve(data_raw.get("out", "data/invoices.jsonl"))}, "data"
    )

    llm_raw = dict(raw.get("llm") or {})
    llm_raw["base_url"] = env.get("LLM_API_BASE") or llm_raw.get("base_url") or ""
    llm_raw["api_key"] = env.get("LLM_API_KEY") or None
    llm = _build(LLMConfig, llm_raw, "llm")

    models_raw = raw.get("models") or {"small": {}, "large": {}}
    _need(bool(models_raw), "models не може бути порожнім")
    models: dict[str, ModelConfig] = {}
    for key, spec in models_raw.items():
        spec = dict(spec or {})
        env_name = f"LLM_MODEL_{key.upper()}"
        spec["model"] = env.get(env_name) or spec.get("model") or None
        models[key] = _build(ModelConfig, spec | {"key": key}, f"models.{key}")

    pipeline = _build(PipelineConfig, raw.get("pipeline") or {}, "pipeline")

    eval_raw = dict(raw.get("eval") or {})
    eval_section = _build(
        EvalConfig,
        eval_raw | {"dataset": resolve(eval_raw.get("dataset", "data/invoices.jsonl"))},
        "eval",
    )
    eval_cfg = EvalConfig(
        dataset=eval_section.dataset,
        models=tuple(eval_section.models),
        results_dir=resolve(eval_raw.get("results_dir", "results")),
        call_log=resolve(eval_raw.get("call_log", "results/calls.jsonl")),
        amount_tolerance=eval_section.amount_tolerance,
        name_edit_distance=eval_section.name_edit_distance,
    )
    for key in eval_cfg.models:
        if key not in models:
            raise ConfigError(f"eval.models посилається на невідому модель: {key}")

    return Config(data=data, llm=llm, models=models, pipeline=pipeline, eval=eval_cfg, raw=raw)
