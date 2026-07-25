from __future__ import annotations

import logging
import os
from functools import lru_cache

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


@lru_cache(maxsize=None)
def configure_telemetry(service_name: str) -> None:
    """Configure OTLP trace, metric, and structured-log export once per process."""
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": os.getenv("LEASH_VERSION", "dev"),
            "deployment.environment.name": os.getenv("DEPLOYMENT_ENVIRONMENT", "demo"),
        }
    )
    if os.getenv("LEASH_DISABLE_OTEL", "false").lower() == "true":
        trace.set_tracer_provider(TracerProvider(resource=resource))
        metrics.set_meter_provider(MeterProvider(resource=resource))
        return
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")
    endpoint = endpoint.replace("http://", "").replace("https://", "")
    insecure = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true"

    # LEASH must remain usable before SigNoz is online. These bounded values
    # keep a missing local collector from delaying shutdown for tens of seconds;
    # a live collector still receives normal OTLP batches.
    export_timeout_millis = int(os.getenv("LEASH_OTLP_EXPORT_TIMEOUT_MS", "1000"))
    export_interval_millis = int(os.getenv("LEASH_OTLP_EXPORT_INTERVAL_MS", "2000"))
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=endpoint, insecure=insecure, timeout=export_timeout_millis / 1000),
            schedule_delay_millis=export_interval_millis,
            export_timeout_millis=export_timeout_millis,
        )
    )
    trace.set_tracer_provider(provider)
    metrics.set_meter_provider(
        MeterProvider(
            resource=resource,
            metric_readers=[
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(endpoint=endpoint, insecure=insecure, timeout=export_timeout_millis / 1000),
                    export_interval_millis=export_interval_millis,
                    export_timeout_millis=export_timeout_millis,
                )
            ],
        )
    )
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(endpoint=endpoint, insecure=insecure, timeout=export_timeout_millis / 1000),
            schedule_delay_millis=export_interval_millis,
            export_timeout_millis=export_timeout_millis,
        )
    )
    set_logger_provider(logger_provider)
    logging.getLogger().addHandler(LoggingHandler(level=logging.INFO, logger_provider=logger_provider))
    HTTPXClientInstrumentor().instrument()


def instrument_app(app, service_name: str) -> None:
    configure_telemetry(service_name)
    FastAPIInstrumentor.instrument_app(app)


def trace_id() -> str:
    context = trace.get_current_span().get_span_context()
    return format(context.trace_id, "032x") if context.trace_id else ""


def meter(name: str):
    return metrics.get_meter(name)
