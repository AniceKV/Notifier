from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path


def extract_body(message):
    plain_text = None
    html = None

    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()

            if content_type == "text/plain" and plain_text is None:
                plain_text = part.get_content()

            elif content_type == "text/html" and html is None:
                html = part.get_content()

    else:
        content_type = message.get_content_type()

        if content_type == "text/plain":
            plain_text = message.get_content()

        elif content_type == "text/html":
            html = message.get_content()

    # Prefer HTML so the email can be displayed as close

    if html:
        return html

    if plain_text:
        return plain_text

    return ""


def parse_email(source):

    if isinstance(source, (str, Path)):
        with open(source, "rb") as f:
            message = BytesParser(policy=policy.default).parse(f)

    elif isinstance(source, bytes):
        message = BytesParser(
            policy=policy.default
        ).parsebytes(source)

    else:
        raise TypeError("source must be a file path or email bytes")

    return {
        "sender": message.get("From"),
        "subject": message.get("Subject"),
        "body": extract_body(message),
        "received_at": parsedate_to_datetime(message.get("Date")),
    }


if __name__ == "__main__":
    print(parse_email("fetched_emails/26638.eml"))
