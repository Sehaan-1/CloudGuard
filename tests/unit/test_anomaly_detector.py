from datetime import date, timedelta

import numpy as np
import pandas as pd

from cloudguard.analysis.anomaly_detector import (
    CompositeDetector,
    to_cost_dataframe,
)
from cloudguard.analysis.iqr_detector import IQRDetector
from cloudguard.analysis.rolling_detector import RollingWindowDetector
from cloudguard.analysis.zscore_detector import ZScoreDetector
from cloudguard.core.models import (
    CloudProviderType,
    CostRecord,
    Severity,
)


def _generate_baseline_records(
    count: int = 30, base_amount: float = 100.0, std: float = 5.0
) -> list[CostRecord]:
    np.random.seed(42)
    start = date(2026, 1, 1)
    records = []
    for i in range(count):
        d = start + timedelta(days=i)
        amt = float(max(10.0, np.random.normal(base_amount, std)))
        records.append(
            CostRecord(
                service="Virtual Machines",
                date=d,
                amount=round(amt, 2),
                provider=CloudProviderType.AZURE,
                region="eastus",
                resource_id="vm-001",
            )
        )
    return records


def test_to_cost_dataframe_empty():
    df = to_cost_dataframe([])
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    assert "amount" in df.columns
    assert "service" in df.columns


def test_to_cost_dataframe_from_records():
    records = _generate_baseline_records(5)
    df = to_cost_dataframe(records)
    assert len(df) == 5
    assert df["amount"].sum() > 0
    assert df["service"].iloc[0] == "Virtual Machines"


def test_zscore_detects_3sigma_outlier():
    records = _generate_baseline_records(30, base_amount=100.0, std=5.0)
    records.append(
        CostRecord(
            service="Virtual Machines",
            date=date(2026, 2, 1),
            amount=500.0,
            provider=CloudProviderType.AZURE,
            region="eastus",
            resource_id="vm-001",
        )
    )

    detector = ZScoreDetector(threshold=3.0, use_rolling=False)
    anomalies = detector.detect(records)

    assert len(anomalies) >= 1
    outlier = next(a for a in anomalies if a.actual_cost >= 450.0)
    assert outlier.deviation_score >= 3.0
    assert outlier.severity in (Severity.HIGH, Severity.CRITICAL)
    assert outlier.is_anomaly is True


def test_zscore_ignores_normal_variation():
    records = _generate_baseline_records(30, base_amount=100.0, std=2.0)
    detector = ZScoreDetector(threshold=3.5, use_rolling=False)
    anomalies = detector.detect(records)
    assert len(anomalies) == 0


def test_zscore_rolling_detector():
    records = _generate_baseline_records(40, base_amount=100.0, std=3.0)
    records.append(
        CostRecord(
            service="Virtual Machines",
            date=date(2026, 2, 11),
            amount=400.0,
            provider=CloudProviderType.AZURE,
            region="eastus",
            resource_id="vm-001",
        )
    )

    detector = ZScoreDetector(threshold=3.0, use_rolling=True, window=14, min_periods=5)
    anomalies = detector.detect(records)

    assert len(anomalies) >= 1
    spike = anomalies[0]
    assert spike.actual_cost == 400.0
    assert spike.deviation_score > 3.0


def test_iqr_detects_outlier_in_skewed_data():
    records = _generate_baseline_records(25, base_amount=50.0, std=4.0)
    records.append(
        CostRecord(
            service="Virtual Machines",
            date=date(2026, 1, 26),
            amount=350.0,
            provider=CloudProviderType.AZURE,
            region="eastus",
            resource_id="vm-001",
        )
    )

    detector = IQRDetector(multiplier=1.5, min_samples=5)
    anomalies = detector.detect(records)

    assert len(anomalies) >= 1
    outlier = anomalies[0]
    assert outlier.actual_cost == 350.0
    assert outlier.method == "iqr"
    assert outlier.deviation_score >= 1.5


def test_iqr_handles_multiple_services():
    records_vm = _generate_baseline_records(20, base_amount=50.0, std=2.0)
    records_s3 = []
    start = date(2026, 1, 1)
    for i in range(20):
        records_s3.append(
            CostRecord(
                service="Storage",
                date=start + timedelta(days=i),
                amount=20.0,
                provider=CloudProviderType.AWS,
                region="us-east-1",
            )
        )
    records_s3.append(
        CostRecord(
            service="Storage",
            date=date(2026, 1, 21),
            amount=150.0,
            provider=CloudProviderType.AWS,
            region="us-east-1",
        )
    )

    all_records = records_vm + records_s3
    detector = IQRDetector(multiplier=1.5, group_by="service")
    anomalies = detector.detect(all_records)

    assert len(anomalies) >= 1
    storage_anomalies = [a for a in anomalies if a.service == "Storage"]
    assert len(storage_anomalies) == 1
    assert storage_anomalies[0].actual_cost == 150.0


def test_rolling_window_detector_sma_and_ewm():
    records = _generate_baseline_records(25, base_amount=100.0, std=3.0)
    records.append(
        CostRecord(
            service="Virtual Machines",
            date=date(2026, 1, 26),
            amount=600.0,
            provider=CloudProviderType.AZURE,
            region="eastus",
        )
    )

    sma_detector = RollingWindowDetector(window=7, std_dev_multiplier=2.5, method="mean")
    sma_anomalies = sma_detector.detect(records)
    assert len(sma_anomalies) >= 1
    assert any(a.actual_cost == 600.0 for a in sma_anomalies)

    ewm_detector = RollingWindowDetector(window=7, std_dev_multiplier=2.5, method="ewm", alpha=0.4)
    ewm_anomalies = ewm_detector.detect(records)
    assert len(ewm_anomalies) >= 1
    assert any(a.actual_cost == 600.0 for a in ewm_anomalies)


def test_composite_detector_voting():
    records = _generate_baseline_records(30, base_amount=100.0, std=2.0)
    records.append(
        CostRecord(
            service="Virtual Machines",
            date=date(2026, 2, 1),
            amount=800.0,
            provider=CloudProviderType.AZURE,
            region="eastus",
            resource_id="vm-spike",
        )
    )

    strat1 = ZScoreDetector(threshold=2.5, use_rolling=False)
    strat2 = IQRDetector(multiplier=1.5)
    strat3 = RollingWindowDetector(window=7, std_dev_multiplier=2.0)

    comp_min_2 = CompositeDetector(strategies=[strat1, strat2, strat3], min_votes=2)
    anomalies = comp_min_2.detect(records)

    assert len(anomalies) >= 1
    composite_outlier = anomalies[0]
    assert composite_outlier.actual_cost == 800.0
    assert composite_outlier.resource_id == "vm-spike"
    assert "composite" in composite_outlier.method
    assert composite_outlier.metadata["votes"] >= 2


def test_composite_detector_requires_min_votes():
    records = _generate_baseline_records(30, base_amount=100.0, std=2.0)
    records.append(
        CostRecord(
            service="Virtual Machines",
            date=date(2026, 2, 1),
            amount=115.0,
            provider=CloudProviderType.AZURE,
            region="eastus",
            resource_id="vm-moderate-spike",
        )
    )

    strat1 = ZScoreDetector(threshold=2.0, use_rolling=False)
    strat2 = ZScoreDetector(threshold=15.0, use_rolling=False)
    strat3 = IQRDetector(multiplier=15.0)

    strict_comp = CompositeDetector(strategies=[strat1, strat2, strat3], min_votes=3)
    anomalies_strict = strict_comp.detect(records)
    assert len(anomalies_strict) == 0

    lenient_comp = CompositeDetector(strategies=[strat1, strat2, strat3], min_votes=1)
    anomalies_lenient = lenient_comp.detect(records)
    assert len(anomalies_lenient) >= 1


def test_rolling_zscore_handles_seasonality():
    records = []
    base_date = date(2026, 1, 1)
    for day in range(60):
        weekday = (base_date + timedelta(days=day)).weekday()
        base_cost = 200.0 if weekday < 5 else 50.0
        records.append(
            CostRecord(
                service="Virtual Machines",
                date=base_date + timedelta(days=day),
                amount=base_cost + float(day % 3),
                provider=CloudProviderType.AZURE,
                region="eastus",
                resource_id="vm-seasonal",
            )
        )

    records.append(
        CostRecord(
            service="Virtual Machines",
            date=base_date + timedelta(days=60),
            amount=900.0,
            provider=CloudProviderType.AZURE,
            region="eastus",
            resource_id="vm-seasonal",
        )
    )

    detector = RollingWindowDetector(window=14, std_dev_multiplier=2.5, min_periods=7)
    anomalies = detector.detect(records)
    assert len(anomalies) >= 1
    assert any(a.actual_cost == 900.0 for a in anomalies)


def test_composite_detector_empty_and_no_votes():
    comp = CompositeDetector(strategies=[])
    assert comp.detect([]) == []

    records = _generate_baseline_records(10, base_amount=100.0, std=1.0)
    strat1 = ZScoreDetector(threshold=10.0, use_rolling=False)
    strat2 = IQRDetector(multiplier=10.0)
    comp_strict = CompositeDetector(strategies=[strat1, strat2], min_votes=1)
    assert comp_strict.detect(records) == []


def test_iqr_detector_empty_and_insufficient_samples():
    detector = IQRDetector(min_samples=10)
    assert detector.detect([]) == []
    few_records = _generate_baseline_records(3)
    assert detector.detect(few_records) == []


def test_zscore_detector_empty_and_insufficient_samples():
    detector = ZScoreDetector(min_periods=10)
    assert detector.detect([]) == []
    few_records = _generate_baseline_records(3)
    assert detector.detect(few_records) == []


def test_rolling_detector_empty_and_insufficient_samples():
    detector = RollingWindowDetector(min_periods=10)
    assert detector.detect([]) == []
    few_records = _generate_baseline_records(3)
    assert detector.detect(few_records) == []
