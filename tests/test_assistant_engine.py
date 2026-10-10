
from app.assistant_engine import interpret_command


def test_list_tasks_command():
    result = interpret_command("show my tasks")

    assert result["intent"] == "list_tasks"
    assert result["requires_approval"] is False


def test_list_pending_tasks_command():
    result = interpret_command("show pending tasks")

    assert result["intent"] == "list_pending_tasks"


def test_create_task_command():
    result = interpret_command("create task: Prepare demo")

    assert result["intent"] == "create_task"
    assert result["parameters"]["title"] == "Prepare demo"


def test_complete_task_command():
    result = interpret_command("complete task 2")

    assert result["intent"] == "complete_task"
    assert result["parameters"]["task_id"] == 2


def test_create_reminder_command():
    result = interpret_command(
        "create reminder: Review demo at 2026-10-12T11:00+05:30"
    )

    assert result["intent"] == "create_reminder"
    assert result["parameters"]["title"] == "Review demo"
    assert result["parameters"]["remind_at"] == "2026-10-12T11:00+05:30"


def test_email_requires_approval():
    result = interpret_command(
        "send email to demo@example.com | "
        "subject: Demo update | body: The demo is ready."
    )

    assert result["intent"] == "propose_email"
    assert result["requires_approval"] is True


def test_calendar_event_requires_approval():
    result = interpret_command(
        "create calendar event Team demo | "
        "start: 2026-10-12T14:00+05:30 | "
        "end: 2026-10-12T14:30+05:30"
    )

    assert result["intent"] == "propose_calendar_event"
    assert result["requires_approval"] is True


def test_unknown_command():
    result = interpret_command("launch a rocket")

    assert result["intent"] == "unknown"


def test_empty_command():
    result = interpret_command("   ")

    assert result["intent"] == "unknown"
