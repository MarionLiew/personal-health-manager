# Medical safety policy

The executable source of truth is `config/medical_safety.yaml` and
`health_agent/safety/response_validator.py`. Responses cannot contain prohibited pseudo-score terms.
Facts are classified as `user_report`, `source_fact`, `clinician_opinion`, `guideline_rule`, or
`system_inference`. An inference is never promoted to diagnosis or clinician opinion.

Only action levels A-E are allowed: immediate real-world care; near-term clinician review; planned
follow-up; observe trends; or evidence does not support a new test. They are routing outputs, not
severity scores. Validated risk percentages may only be implemented with a named public model,
versioned source, complete parameters, applicability/exclusion checks, deterministic calculation,
and retained inputs. No such production model is bundled in v0.1.0.

CTDIvol/DLP are scanner output indices. Effective-dose estimates are coarse comparisons, are stored
separately from machine values, and must not be converted into a personal cancer probability or a
"radiation balance". Wearables and single consumer-scale measurements cannot diagnose disease.

