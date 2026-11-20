"""Unit tests for logging system in cloudguard.core.logging."""

import io
import logging

from cloudguard.core.logging import get_logger, setup_logging


def test_setup_logging_with_rich():
    stream = io.StringIO()
    logger = setup_logging(level="DEBUG", stream=stream, use_rich=True)
    assert logger.level == logging.DEBUG
    logger.info("Test rich logging message")


def test_setup_logging_standard():
    stream = io.StringIO()
    logger = setup_logging(level="INFO", stream=stream, use_rich=False)
    assert logger.level == logging.INFO
    logger.info("Test standard logging output")
    output = stream.getvalue()
    assert "Test standard logging output" in output
    assert "INFO" in output


def test_get_logger_namespacing():
    log1 = get_logger("engine")
    assert log1.name == "cloudguard.engine"

    log2 = get_logger("cloudguard.providers.mock")
    assert log2.name == "cloudguard.providers.mock"
