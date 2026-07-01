"""services/external_api — Juno's outbound HTTP clients for external APIs."""
from .athena_client import athena_client, AthenaClient

__all__ = ["athena_client", "AthenaClient"]
