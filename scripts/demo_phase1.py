"""Demo script showcasing Phase 1 capabilities of CloudGuard."""

import asyncio
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from cloudguard import CostAnalysisEngine


async def main() -> None:
    print("=" * 70)
    print("[*] CloudGuard FinOps Platform - Phase 1 Foundation & Architecture Demo")
    print("=" * 70)

    engine = CostAnalysisEngine(provider="mock")
    print(f"\n[1] Connected to Provider: {engine.provider.provider_name()}")
    connected = await engine.test_connection()
    print(f"    Health Status: {'ONLINE' if connected else 'OFFLINE'}")

    print("\n[2] Executing Cloud Infrastructure Audit Scan...")
    scan = await engine.scan_infrastructure()
    print(f"    Total Resources Scanned: {scan.total_resources_scanned}")
    print(f"    Idle Compute Instances (<5% CPU): {scan.idle_count}")
    print(f"    Orphaned / Unattached Storage Disks: {scan.orphaned_count}")
    print(f"    Underutilized VMs (Rightsizing candidates): {scan.underutilized_count}")
    print(f"    Untagged Resources (Governance alert): {scan.untagged_count}")
    print(f"    Estimated Monthly Waste: ${scan.total_waste_monthly:,.2f}")

    print("\n    Waste Breakdown Highlights:")
    for vm in scan.idle_resources:
        print(
            f"      - [IDLE VM] {vm.name} ({vm.region}): {vm.utilization_pct:.1f}% CPU, ${vm.monthly_cost:,.2f}/mo"
        )
    for disk in scan.orphaned_storage:
        print(
            f"      - [ORPHAN DISK] {disk.name} ({disk.region}): Unattached, ${disk.monthly_cost:,.2f}/mo"
        )

    print("\n[3] Calculating 30-Day Cost Consumption Summary...")
    cost = await engine.get_cost_summary()
    print(f"    Period: {cost.period_start} to {cost.period_end}")
    print(f"    Total Cost: ${cost.total_cost:,.2f} across {cost.record_count} line items")
    print(f"    Average Daily Spend: ${cost.average_daily_cost:,.2f}")

    print("\n    Top Spending Services:")
    for svc, amount in cost.top_services[:5]:
        pct = (amount / cost.total_cost) * 100 if cost.total_cost > 0 else 0
        print(f"      - {svc:25s}: ${amount:10,.2f}  ({pct:5.1f}%)")

    print("\n" + "=" * 70)
    print("[SUCCESS] Phase 1 Architecture Verification Complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
