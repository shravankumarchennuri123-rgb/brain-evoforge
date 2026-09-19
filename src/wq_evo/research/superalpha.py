from __future__ import annotations

import logging
import os
from typing import Any

from ..brain.client import BrainClient
from ..brain.errors import BrainError
from ..models import ResearchProfile

LOG = logging.getLogger(__name__)


class SuperAlphaAdapter:
    """Dynamic SuperAlpha adapter.

    BRAIN's exact SUPER simulation schema is account/tier sensitive and can
    evolve. This adapter never assumes a hidden schema. It first inspects live
    simulation options and existing SUPER alpha shapes. When those capabilities
    are not discoverable, it returns an explicit unsupported state instead of
    guessing a write payload.
    """

    def __init__(self, client: BrainClient, profile: ResearchProfile):
        self.client = client
        self.profile = profile

    def discover(self, alphas: list[dict[str, Any]], simulation_options: dict[str, Any]) -> dict[str, Any]:
        super_rows = [a for a in alphas if str(a.get("type", "")).upper() == "SUPER"]
        active_regular = [a for a in alphas if str(a.get("type", "")).upper() == "REGULAR" and str(a.get("status", "")).upper() == "ACTIVE"]
        return {
            "type_supported": self._type_supported(simulation_options),
            "existing_super_shape": bool(super_rows),
            "active_regular_count": len(active_regular),
            "existing_super": super_rows,
        }

    @staticmethod
    def _type_supported(options: dict[str, Any]) -> bool:
        raw = str(options).upper()
        return "SUPER" in raw

    def build_payload(self, *, selection_expression: str, combo_expression: str, existing_super: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
        """Build from an existing account-native SUPER shape when possible.

        Fallback: a user-provided captured template. No invented SUPER wire schema is used.
        """
        import json
        template = None
        if existing_super:
            src = existing_super[0]
            # Clone only the fields relevant to creating another object; platform-generated
            # identifiers/status/metrics are intentionally removed.
            template = {k: json.loads(json.dumps(src[k])) for k in ("type", "settings", "selection", "combo") if k in src}
        template_path = os.getenv("WQ_SUPER_TEMPLATE_JSON")
        if template is None and template_path:
            try:
                with open(template_path, "r", encoding="utf-8") as fh:
                    template = json.load(fh)
            except Exception as exc:
                raise BrainError(f"invalid WQ_SUPER_TEMPLATE_JSON: {exc}") from exc
        if template is None:
            return None
        if not isinstance(template, dict) or str(template.get("type", "")).upper() != "SUPER":
            raise BrainError("super template must be an object with type=SUPER")
        payload = json.loads(json.dumps(template))
        if "selection" in payload:
            if isinstance(payload["selection"], dict): payload["selection"]["code"] = selection_expression
            else: payload["selection"] = selection_expression
        if "combo" in payload:
            if isinstance(payload["combo"], dict): payload["combo"]["code"] = combo_expression
            else: payload["combo"] = combo_expression
        return payload
