"""Research package — experiment contracts and validation (P4)."""

from research.experiment_spec import (
    EXPERIMENT_SPEC_SCHEMA_VERSION,
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
from research.validation import (
    SCHEMA_PATH,
    assert_no_secrets,
    load_json_schema,
    validate_against_json_schema,
)

__all__ = [
    "EXPERIMENT_SPEC_SCHEMA_VERSION",
    "SCHEMA_PATH",
    "DatasetManifestRef",
    "ExperimentSpec",
    "FeeAssumption",
    "FundingAssumption",
    "SlippageAssumption",
    "TimeRange",
    "assert_no_secrets",
    "dumps_canonical",
    "load_experiment_spec",
    "load_json_schema",
    "parse_experiment_spec",
    "save_experiment_spec",
    "to_canonical_dict",
    "validate_against_json_schema",
]
