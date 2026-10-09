"""Unit tests for core/log.py (flow logging, dfx layer)."""
import io
import logging

from core.log import get_flow_logger, set_flow_log_level


def _capture(logger):
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    logger.addHandler(handler)
    return buf, handler


def _release(logger, handler):
    logger.removeHandler(handler)


def test_logger_is_process_wide_singleton():
    assert get_flow_logger() is get_flow_logger()
    assert get_flow_logger().name == "autocelllibx"


def test_logger_emits_info():
    logger = get_flow_logger()
    buf, handler = _capture(logger)
    try:
        logger.info("marker message")
        assert "marker message" in buf.getvalue()
    finally:
        _release(logger, handler)


def test_set_level_filters_debug():
    logger = get_flow_logger()
    set_flow_log_level(logging.WARNING)
    try:
        buf, handler = _capture(logger)
        try:
            logger.info("hidden")
            logger.warning("shown")
            assert "hidden" not in buf.getvalue()
            assert "shown" in buf.getvalue()
        finally:
            _release(logger, handler)
    finally:
        set_flow_log_level(logging.INFO)
