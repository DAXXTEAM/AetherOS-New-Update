"""Tests for AetherOS Notifications Module."""
import pytest
from notifications.manager import NotificationManager, NotificationPriority
from notifications.channels import ConsoleChannel, WebhookChannel


class TestNotificationManager:
    def test_send(self):
        nm = NotificationManager()
        result = nm.send("Test", "Hello", NotificationPriority.NORMAL)
        assert result
        assert nm.stats["total_delivered"] == 1

    def test_history(self):
        nm = NotificationManager()
        nm.send("T1", "M1")
        nm.send("T2", "M2")
        history = nm.get_history()
        assert len(history) == 2

    def test_unknown_channel(self):
        nm = NotificationManager()
        result = nm.send("Test", "Hello", channel="unknown")
        assert not result


class TestChannels:
    def test_console(self):
        ch = ConsoleChannel()
        assert ch.name == "console"
        assert ch.send("title", "msg")

    def test_webhook(self):
        ch = WebhookChannel(url="https://example.com/hook")
        assert ch.name == "webhook"
        assert ch.send("title", "msg")
