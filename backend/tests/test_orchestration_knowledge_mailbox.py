from __future__ import annotations

from types import SimpleNamespace

from app.modules.orchestration import service


class _FakeRunnerClient:
    def create_mailbox_note(self, body):
        return {
            "id": "mailbox_1",
            "direction": "inbox",
            "type": body["type"],
            "subject": body["subject"],
            "body": body["body"],
            "job_id": body["job_id"],
            "run_id": body["run_id"],
            "severity": body["severity"],
            "from": body["from"],
            "to": body["to"],
            "attachments": body["attachments"],
            "tags": body["tags"],
            "metadata": body["metadata"],
        }


def test_create_mailbox_note_queries_and_promotes_mail_knowledge(monkeypatch) -> None:
    node = SimpleNamespace(id="devwork", label="Devwork", base_url="http://devwork:8090")
    search_calls = {}
    write_calls = {}

    monkeypatch.setattr(service, "get_node", lambda session, node_id: node)
    monkeypatch.setattr(service, "_runner_client_for_node", lambda current: _FakeRunnerClient())

    def fake_search(query, *, filters=None, limit=5):
        search_calls["query"] = query
        search_calls["filters"] = filters
        search_calls["limit"] = limit
        return [{"title": "Prior founder follow-up", "summary": "Keep it short", "record_type": "followup_pattern", "topic": "founder_outreach"}]

    def fake_add_mail_record(**kwargs):
        write_calls.update(kwargs)
        return {"ok": True, "id": "mail_knowledge_1"}

    monkeypatch.setattr(service, "search_mail_knowledge", fake_search)
    monkeypatch.setattr(service, "maybe_add_mail_record", fake_add_mail_record)

    note = service.create_mailbox_note(
        None,
        "devwork",
        {
            "type": "handoff",
            "subject": "Founder outreach fallback",
            "body": "If no reply after two touches, switch to short case-study follow-up.",
            "tags": ["mail", "reusable", "followup"],
            "metadata": {
                "save_to_knowledge": True,
                "knowledge_record_type": "followup_pattern",
                "knowledge_topic": "founder_outreach",
            },
        },
    )

    assert search_calls["query"] == "Founder outreach fallback"
    assert search_calls["filters"]["topic"] == "founder_outreach"
    assert note["metadata"]["knowledge_matches_count"] == 1
    assert write_calls["record_type"] == "followup_pattern"
    assert write_calls["topic"] == "founder_outreach"
    assert write_calls["metadata"]["node_id"] == "devwork"
    assert note["metadata"]["knowledge_write"]["ok"] is True
