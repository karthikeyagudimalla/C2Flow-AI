
import re


def interpret_command(message: str) -> dict:
    """Interpret supported Garuda Ops commands without calling an AI API."""
    text = message.strip()

    if not text:
        return {
            "intent": "unknown",
            "message": "Please enter a command.",
            "requires_approval": False,
        }

    normalized = re.sub(r"\s+", " ", text).lower()

    if re.fullmatch(r"(show|list|view|get) (my )?tasks", normalized):
        return {
            "intent": "list_tasks",
            "message": "I'll retrieve your tasks.",
            "requires_approval": False,
        }

    if re.fullmatch(
        r"(show|list|view|get) (my )?reminders", normalized
    ):
        return {
            "intent": "list_reminders",
            "message": "I'll retrieve your reminders.",
            "requires_approval": False,
        }

    if re.fullmatch(
        r"(show|list|view|get) (my )?workflows", normalized
    ):
        return {
            "intent": "list_workflows",
            "message": "I'll retrieve your workflows.",
            "requires_approval": False,
        }

    if re.fullmatch(r"(show|list|view|get) pending tasks", normalized):
        return {
            "intent": "list_pending_tasks",
            "message": "I'll retrieve your pending tasks.",
            "requires_approval": False,
        }

    task_match = re.fullmatch(
        r"(?:create|add|make) (?:a )?task:?\s+(.+)",
        text,
        flags=re.IGNORECASE,
    )
    if task_match:
        title = task_match.group(1).strip()
        if title:
            return {
                "intent": "create_task",
                "parameters": {"title": title},
                "message": f"I can create the task: {title}",
                "requires_approval": False,
            }

    
    email_match = re.fullmatch(
        r"send email to\s+(\S+)\s+\|\s*subject:\s*(.+?)"
        r"\s+\|\s*body:\s*(.+)",
        text,
        flags=re.IGNORECASE,
    )
    if email_match:
        recipient, subject, body = email_match.groups()

        return {
            "intent": "propose_email",
            "parameters": {
                "to": recipient.strip(),
                "subject": subject.strip(),
                "body": body.strip(),
            },
            "message": "I'll prepare this email for your approval.",
            "requires_approval": True,
        }

    if re.search(
        r"\b(send an email|send email|email someone)\b",
        normalized,
    ):
        return {
            "intent": "propose_email",
            "message": (
                "I'll prepare an email proposal for your review. "
                "Please provide the recipient, subject, and body."
            ),
            "requires_approval": True,
        }


    
    calendar_match = re.fullmatch(
        r"create calendar event\s+(.+?)\s+\|\s*start:\s*(\S+)"
        r"\s+\|\s*end:\s*(\S+)",
        text,
        flags=re.IGNORECASE,
    )
    if calendar_match:
        title, start, end = calendar_match.groups()

        return {
            "intent": "propose_calendar_event",
            "parameters": {
                "title": title.strip(),
                "start": start.strip(),
                "end": end.strip(),
            },
            "message": "I'll prepare this calendar event for your approval.",
            "requires_approval": True,
        }

    if re.search(
        r"\b(create a calendar event|schedule a meeting|"
        r"add a calendar event)\b",
        normalized,
    ):
        return {
            "intent": "propose_calendar_event",
            "message": (
                "I'll prepare a calendar event proposal for your review. "
                "Please provide its title, start time, and end time."
            ),
            "requires_approval": True,
        }


    
    
    reminder_match = re.fullmatch(
        r"(?:create|add) reminder:?\s+(.+?)\s+at\s+"
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?:\+\d{2}:\d{2}|Z))",
        text,
        flags=re.IGNORECASE,
    )
    if reminder_match:
        title = reminder_match.group(1).strip()
        remind_at = reminder_match.group(2)

        if title:
            return {
                "intent": "create_reminder",
                "parameters": {
                    "title": title,
                    "remind_at": remind_at,
                },
                "message": f"I can schedule the reminder: {title}",
                "requires_approval": False,
            }


    
    complete_match = re.fullmatch(
        r"(?:complete|finish|mark complete) task\s+#?(\d+)",
        normalized,
    )
    if complete_match:
        return {
            "intent": "complete_task",
            "parameters": {"task_id": int(complete_match.group(1))},
            "message": f"I can mark task {complete_match.group(1)} as completed.",
            "requires_approval": False,
        }


    return {
        "intent": "unknown",
        "message": (
            "I don't recognize that command yet. Try 'show my tasks', "
            "'show my reminders', 'show my workflows', or 'create task: "
            "Prepare demo'."
        ),
        "requires_approval": False,
    }
