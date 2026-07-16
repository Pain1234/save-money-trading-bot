"""Research package — P4 experiment pipeline."""

from research.costs import (
    COST_MODEL_VERSION,
    CostScenario,
    base_cost_scenario,
    cost_manifest_fields,
    cost_models_from_spec,
    require_cost_fields,
)
from research.experiment_spec import (
    EXPERIMENT_SPEC_SCHEMA_VERSION,
    CostScenarioSpec,
    DatasetManifestRef,
    ExperimentSpec,
    FeeAssumption,
    FundingAssumption,
    SlippageAssumption,
    TimeRange,
    dumps_canonical,
    load_experiment_spec,
    parse_experiment_spec,
    save_experiment_spec,
    to_canonical_dict,
)
from research.identity import (
    RunIdentityInputs,
    compute_experiment_id,
    compute_run_id,
    new_attempt_id,
    semantic_artifact_hash,
    semantic_spec_dict,
)
from research.metrics_contract import (
    METRICS_SCHEMA_VERSION,
    BenchmarkRef,
    ResearchMetrics,
    parse_benchmark_ref,
)
from research.registry import ExperimentRegistry
from research.run_manifest import (
    RUN_MANIFEST_SCHEMA_VERSION,
    RunManifest,
    build_run_manifest,
    load_run_manifest,
    save_run_manifest,
)
from research.runner import RunOutcome, RunRequest, run_experiment
from research.strategy_resolver import ResolvedStrategy, resolve_strategy
from research.validation import (
    SCHEMA_PATH,
    assert_no_secrets,
    load_json_schema,
    validate_against_json_schema,
)

__all__ = [
    "COST_MODEL_VERSION",
    "EXPERIMENT_SPEC_SCHEMA_VERSION",
    "METRICS_SCHEMA_VERSION",
    "RUN_MANIFEST_SCHEMA_VERSION",
    "SCHEMA_PATH",
    "BenchmarkRef",
    "CostScenario",
    "CostScenarioSpec",
    "DatasetManifestRef",
    "ExperimentRegistry",
    "ExperimentSpec",
    "FeeAssumption",
    "FundingAssumption",
    "ResearchMetrics",
    "ResolvedStrategy",
    "RunIdentityInputs",
    "RunManifest",
    "RunOutcome",
    "RunRequest",
    "SlippageAssumption",
    "TimeRange",
    "assert_no_secrets",
    "base_cost_scenario",
    "build_run_manifest",
    "compute_experiment_id",
    "compute_run_id",
    "cost_manifest_fields",
    "cost_models_from_spec",
    "dumps_canonical",
    "load_experiment_spec",
    "load_json_schema",
    "load_run_manifest",
    "new_attempt_id",
    "parse_benchmark_ref",
    "parse_experiment_spec",
    "require_cost_fields",
    "resolve_strategy",
    "run_experiment",
    "save_experiment_spec",
    "save_run_manifest",
    "semantic_artifact_hash",
    "semantic_spec_dict",
    "to_canonical_dict",
    "validate_against_json_schema",
]
