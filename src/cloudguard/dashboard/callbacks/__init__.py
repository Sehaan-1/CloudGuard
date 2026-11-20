from __future__ import annotations

import dash

from cloudguard.dashboard.callbacks.anomaly_cb import register_anomaly_callbacks
from cloudguard.dashboard.callbacks.cost_cb import register_cost_callbacks
from cloudguard.dashboard.callbacks.overview_cb import register_overview_callbacks
from cloudguard.dashboard.callbacks.resource_cb import register_resource_callbacks


def register_callbacks(app: dash.Dash) -> None:
    register_overview_callbacks(app)
    register_cost_callbacks(app)
    register_anomaly_callbacks(app)
    register_resource_callbacks(app)


__all__ = ["register_callbacks"]
