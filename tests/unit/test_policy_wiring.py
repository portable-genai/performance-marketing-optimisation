from types import SimpleNamespace

from performance_marketing.api.deps import make_report_service
from performance_marketing.config import PolicySettings


def test_adopter_policy_overrides_are_wired_into_deterministic_engines() -> None:
    marker = object()
    container = SimpleNamespace(
        settings=SimpleNamespace(
            policy=PolicySettings(
                attribution_first_weight=0.2,
                attribution_last_weight=0.3,
                significance_alpha=0.01,
                significance_min_sample_per_arm=500,
                optimisation_max_step_fraction=0.1,
                anomaly_z_threshold=2.0,
                anomaly_high_threshold=3.0,
                anomaly_critical_threshold=5.0,
            )
        ),
        metrics=marker,
        ad_platform=marker,
        llm=marker,
        guardrail=marker,
        tracer=marker,
        audit=marker,
        review_router=None,
    )
    service = make_report_service(container)
    assert service._attribution.first_weight == 0.2
    assert service._significance.alpha == 0.01
    assert service._optimisation.max_step_fraction == 0.1
    assert service._anomaly.z_threshold == 2.0
