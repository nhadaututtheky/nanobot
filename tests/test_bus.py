"""Unit tests for MessageBus (nanobot/bus/queue.py)."""

import asyncio

import pytest

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_inbound(
    channel: str = "telegram",
    sender_id: str = "user1",
    chat_id: str = "42",
    content: str = "hello",
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        chat_id=chat_id,
        content=content,
    )


def make_outbound(
    channel: str = "telegram",
    chat_id: str = "42",
    content: str = "world",
) -> OutboundMessage:
    return OutboundMessage(channel=channel, chat_id=chat_id, content=content)


# ---------------------------------------------------------------------------
# MessageBus.publish_inbound / consume_inbound
# ---------------------------------------------------------------------------


class TestInboundQueue:
    async def test_publish_then_consume_returns_same_message(self) -> None:
        bus = MessageBus()
        msg = make_inbound(content="ping")
        await bus.publish_inbound(msg)
        received = await bus.consume_inbound()
        assert received is msg

    async def test_consume_preserves_all_fields(self) -> None:
        bus = MessageBus()
        msg = make_inbound(channel="slack", sender_id="alice", chat_id="C001", content="hi there")
        await bus.publish_inbound(msg)
        received = await bus.consume_inbound()
        assert received.channel == "slack"
        assert received.sender_id == "alice"
        assert received.chat_id == "C001"
        assert received.content == "hi there"

    async def test_multiple_messages_consumed_fifo(self) -> None:
        bus = MessageBus()
        msgs = [make_inbound(content=f"msg{i}") for i in range(5)]
        for m in msgs:
            await bus.publish_inbound(m)
        for expected in msgs:
            received = await bus.consume_inbound()
            assert received is expected

    async def test_inbound_size_reflects_queued_count(self) -> None:
        bus = MessageBus()
        assert bus.inbound_size == 0
        for i in range(3):
            await bus.publish_inbound(make_inbound(content=f"m{i}"))
        assert bus.inbound_size == 3

    async def test_inbound_size_decreases_after_consume(self) -> None:
        bus = MessageBus()
        await bus.publish_inbound(make_inbound())
        await bus.publish_inbound(make_inbound())
        assert bus.inbound_size == 2
        await bus.consume_inbound()
        assert bus.inbound_size == 1
        await bus.consume_inbound()
        assert bus.inbound_size == 0

    async def test_consume_inbound_blocks_on_empty_queue(self) -> None:
        bus = MessageBus()
        # consume_inbound must block when the queue is empty
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(bus.consume_inbound(), timeout=0.05)

    async def test_consume_unblocks_after_publish(self) -> None:
        bus = MessageBus()

        async def delayed_publish() -> None:
            await asyncio.sleep(0.02)
            await bus.publish_inbound(make_inbound(content="late"))

        asyncio.create_task(delayed_publish())
        received = await asyncio.wait_for(bus.consume_inbound(), timeout=0.5)
        assert received.content == "late"

    async def test_session_key_property_on_received_message(self) -> None:
        bus = MessageBus()
        msg = make_inbound(channel="discord", chat_id="srv99")
        await bus.publish_inbound(msg)
        received = await bus.consume_inbound()
        assert received.session_key == "discord:srv99"

    async def test_session_key_override_respected(self) -> None:
        bus = MessageBus()
        msg = InboundMessage(
            channel="telegram",
            sender_id="u1",
            chat_id="42",
            content="test",
            session_key_override="thread:special",
        )
        await bus.publish_inbound(msg)
        received = await bus.consume_inbound()
        assert received.session_key == "thread:special"


# ---------------------------------------------------------------------------
# MessageBus.publish_outbound / consume_outbound
# ---------------------------------------------------------------------------


class TestOutboundQueue:
    async def test_publish_then_consume_returns_same_message(self) -> None:
        bus = MessageBus()
        msg = make_outbound(content="pong")
        await bus.publish_outbound(msg)
        received = await bus.consume_outbound()
        assert received is msg

    async def test_consume_preserves_all_fields(self) -> None:
        bus = MessageBus()
        msg = make_outbound(channel="slack", chat_id="C999", content="answer here")
        await bus.publish_outbound(msg)
        received = await bus.consume_outbound()
        assert received.channel == "slack"
        assert received.chat_id == "C999"
        assert received.content == "answer here"

    async def test_multiple_messages_consumed_fifo(self) -> None:
        bus = MessageBus()
        msgs = [make_outbound(content=f"reply{i}") for i in range(4)]
        for m in msgs:
            await bus.publish_outbound(m)
        for expected in msgs:
            received = await bus.consume_outbound()
            assert received is expected

    async def test_outbound_size_reflects_queued_count(self) -> None:
        bus = MessageBus()
        assert bus.outbound_size == 0
        for _ in range(2):
            await bus.publish_outbound(make_outbound())
        assert bus.outbound_size == 2

    async def test_outbound_size_decreases_after_consume(self) -> None:
        bus = MessageBus()
        await bus.publish_outbound(make_outbound())
        await bus.publish_outbound(make_outbound())
        assert bus.outbound_size == 2
        await bus.consume_outbound()
        assert bus.outbound_size == 1
        await bus.consume_outbound()
        assert bus.outbound_size == 0

    async def test_consume_outbound_blocks_on_empty_queue(self) -> None:
        bus = MessageBus()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(bus.consume_outbound(), timeout=0.05)

    async def test_consume_unblocks_after_publish(self) -> None:
        bus = MessageBus()

        async def delayed_publish() -> None:
            await asyncio.sleep(0.02)
            await bus.publish_outbound(make_outbound(content="delayed"))

        asyncio.create_task(delayed_publish())
        received = await asyncio.wait_for(bus.consume_outbound(), timeout=0.5)
        assert received.content == "delayed"

    async def test_reply_to_field_preserved(self) -> None:
        bus = MessageBus()
        msg = OutboundMessage(channel="tg", chat_id="1", content="reply", reply_to="msg_id_99")
        await bus.publish_outbound(msg)
        received = await bus.consume_outbound()
        assert received.reply_to == "msg_id_99"

    async def test_media_and_metadata_preserved(self) -> None:
        bus = MessageBus()
        msg = OutboundMessage(
            channel="tg",
            chat_id="1",
            content="with extras",
            media=["http://example.com/img.png"],
            metadata={"parse_mode": "Markdown"},
        )
        await bus.publish_outbound(msg)
        received = await bus.consume_outbound()
        assert received.media == ["http://example.com/img.png"]
        assert received.metadata["parse_mode"] == "Markdown"


# ---------------------------------------------------------------------------
# Inbound and Outbound queues are independent
# ---------------------------------------------------------------------------


class TestQueueIsolation:
    async def test_inbound_and_outbound_queues_are_independent(self) -> None:
        bus = MessageBus()
        inbound_msg = make_inbound(content="from channel")
        outbound_msg = make_outbound(content="from agent")

        await bus.publish_inbound(inbound_msg)
        await bus.publish_outbound(outbound_msg)

        # Each queue has exactly one item
        assert bus.inbound_size == 1
        assert bus.outbound_size == 1

        got_inbound = await bus.consume_inbound()
        got_outbound = await bus.consume_outbound()

        assert got_inbound.content == "from channel"
        assert got_outbound.content == "from agent"

        assert bus.inbound_size == 0
        assert bus.outbound_size == 0

    async def test_consuming_inbound_does_not_affect_outbound(self) -> None:
        bus = MessageBus()
        await bus.publish_outbound(make_outbound(content="outbound only"))
        # Consuming inbound on empty queue should timeout, not drain outbound
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(bus.consume_inbound(), timeout=0.05)
        # Outbound message must still be there
        assert bus.outbound_size == 1

    async def test_consuming_outbound_does_not_affect_inbound(self) -> None:
        bus = MessageBus()
        await bus.publish_inbound(make_inbound(content="inbound only"))
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(bus.consume_outbound(), timeout=0.05)
        assert bus.inbound_size == 1

    async def test_full_roundtrip_channel_to_agent_to_channel(self) -> None:
        bus = MessageBus()

        # Simulate channel pushing a user message
        user_msg = make_inbound(channel="telegram", chat_id="100", content="What time is it?")
        await bus.publish_inbound(user_msg)

        # Simulate agent processing and responding
        received = await bus.consume_inbound()
        assert received.content == "What time is it?"
        response = OutboundMessage(
            channel=received.channel,
            chat_id=received.chat_id,
            content="It is noon.",
        )
        await bus.publish_outbound(response)

        # Simulate channel reading the reply
        reply = await bus.consume_outbound()
        assert reply.channel == "telegram"
        assert reply.chat_id == "100"
        assert reply.content == "It is noon."


# ---------------------------------------------------------------------------
# Concurrent producers / consumers
# ---------------------------------------------------------------------------


class TestConcurrentAccess:
    async def test_concurrent_producers_all_messages_consumed(self) -> None:
        bus = MessageBus()
        n = 20

        async def producer(idx: int) -> None:
            await bus.publish_inbound(make_inbound(content=f"item{idx}"))

        await asyncio.gather(*(producer(i) for i in range(n)))
        assert bus.inbound_size == n

        contents = set()
        for _ in range(n):
            msg = await bus.consume_inbound()
            contents.add(msg.content)
        assert len(contents) == n
        assert all(f"item{i}" in contents for i in range(n))

    async def test_concurrent_consumer_receives_each_message_once(self) -> None:
        bus = MessageBus()
        n = 10
        for i in range(n):
            await bus.publish_inbound(make_inbound(content=f"once{i}"))

        results: list[str] = []

        async def consumer() -> None:
            for _ in range(n // 2):
                msg = await bus.consume_inbound()
                results.append(msg.content)

        await asyncio.gather(consumer(), consumer())
        assert len(results) == n
        assert len(set(results)) == n  # no duplicates
