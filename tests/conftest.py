import os

# Unit and contract tests exercise policy behavior, not collector delivery.
# Disabling exporters prevents background retry threads from delaying test exit.
os.environ.setdefault("LEASH_DISABLE_OTEL", "true")
