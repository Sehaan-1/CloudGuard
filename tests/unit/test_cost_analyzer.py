from datetime import date, timedelta

from cloudguard.analysis.cost_analyzer import CostAnalyzer
from cloudguard.core.models import CloudProviderType, CostRecord


def _create_sample_cost_dataset() -> list[CostRecord]:
    records = []
    base_date = date(2026, 1, 1)

    for i in range(60):
        cur_date = base_date + timedelta(days=i)
        records.append(
            CostRecord(
                service="Virtual Machines",
                date=cur_date,
                amount=100.0 + (i * 0.5),
                provider=CloudProviderType.AZURE,
                region="eastus",
            )
        )
        records.append(
            CostRecord(
                service="Storage",
                date=cur_date,
                amount=30.0 + (i * 0.1),
                provider=CloudProviderType.AZURE,
                region="eastus",
            )
        )
        records.append(
            CostRecord(
                service="Database",
                date=cur_date,
                amount=50.0,
                provider=CloudProviderType.AZURE,
                region="westus",
            )
        )
    return records


def test_cost_analyzer_mom_growth():
    records = _create_sample_cost_dataset()
    analyzer = CostAnalyzer(records)
    res = analyzer.calculate_mom_growth()

    assert "monthly_totals" in res
    assert "overall_mom_pct" in res
    assert "monthly_growth_breakdown" in res
    assert "service_mom_growth" in res
    assert len(res["monthly_totals"]) >= 2
    assert "Virtual Machines" in res["service_mom_growth"]


def test_cost_analyzer_daily_burn_rate():
    records = _create_sample_cost_dataset()
    analyzer = CostAnalyzer(records)
    burn = analyzer.calculate_daily_burn_rate()

    assert burn["average_daily_cost"] > 0.0
    assert burn["recent_7d_average"] > 0.0
    assert burn["projected_monthly_run_rate"] > 0.0
    assert burn["max_daily_cost"] >= burn["min_daily_cost"]
    assert len(burn["daily_totals"]) == 60


def test_cost_analyzer_top_cost_drivers():
    records = _create_sample_cost_dataset()
    analyzer = CostAnalyzer(records)
    drivers = analyzer.identify_top_cost_drivers(top_n=3)

    assert len(drivers) == 3
    assert drivers[0]["service"] == "Virtual Machines"
    assert drivers[0]["percentage_of_total"] > drivers[1]["percentage_of_total"]
    assert "trend" in drivers[0]
    assert drivers[0]["trend"] in ("growing", "declining", "stable")


def test_cost_analyzer_project_costs():
    records = _create_sample_cost_dataset()
    analyzer = CostAnalyzer(records)
    proj = analyzer.project_costs(days_ahead=15)

    assert "slope" in proj
    assert "r_squared" in proj
    assert "projected_cost_next_period" in proj
    assert len(proj["projections"]) == 15
    assert proj["projected_cost_next_period"] > 0.0


def test_cost_analyzer_service_breakdown():
    records = _create_sample_cost_dataset()
    analyzer = CostAnalyzer(records)
    breakdown = analyzer.get_service_breakdown_trends()

    assert "service_totals" in breakdown
    assert "region_totals" in breakdown
    assert "Virtual Machines" in breakdown["service_totals"]
    assert "eastus" in breakdown["region_totals"]


def test_cost_analyzer_full_analysis():
    records = _create_sample_cost_dataset()
    analyzer = CostAnalyzer(records)
    full = analyzer.full_analysis(days_ahead=30, top_n=5)

    assert "mom_growth" in full
    assert "burn_rate" in full
    assert "top_cost_drivers" in full
    assert "projections" in full
    assert "service_breakdown" in full


def test_cost_analyzer_empty_dataset():
    analyzer = CostAnalyzer([])
    mom = analyzer.calculate_mom_growth()
    assert mom["overall_mom_pct"] == 0.0
    assert mom["monthly_totals"] == {}

    burn = analyzer.calculate_daily_burn_rate()
    assert burn["average_daily_cost"] == 0.0

    drivers = analyzer.identify_top_cost_drivers()
    assert drivers == []

    proj = analyzer.project_costs()
    assert proj["slope"] == 0.0
