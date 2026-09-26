"""OpenTelemetry setup (PLAN §38). No-op unless OTEL_EXPORTER_OTLP_ENDPOINT is set."""

import logging
import time
from contextlib import contextmanager

from opentelemetry import trace

from app.config import Settings

log = logging.getLogger(__name__)
tracer = trace.get_tracer("memory-engine")


def setup_tracing(settings: Settings, app=None) -> None:
    if not settings.otel_exporter_otlp_endpoint:
        return
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": "memory-engine",
                                                            "deployment.environment": settings.environment}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)))
        trace.set_tracer_provider(provider)
        if app is not None:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        log.warning("OTEL endpoint set but opentelemetry exporter extras are not installed (pip install .[otel])")


class StepTimer:
    """Collects {name, latency_ms, detail} steps for the user-visible trace and emits spans."""

    def __init__(self):
        self.steps: list[dict] = []

    @contextmanager
    def step(self, name: str, **attrs):
        start = time.perf_counter()
        record: dict = {"name": name}
        with tracer.start_as_current_span(name) as span:
            for k, v in attrs.items():
                span.set_attribute(k, v if isinstance(v, (str, int, float, bool)) else str(v))
            try:
                yield record
            finally:
                record["latency_ms"] = int((time.perf_counter() - start) * 1000)
                span.set_attribute("latency_ms", record["latency_ms"])
                self.steps.append(record)
