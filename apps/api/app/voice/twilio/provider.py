"""Twilio Voice TwiML helpers + provider."""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from typing import Protocol
from xml.sax.saxutils import escape

from app.sms.twilio.provider import validate_twilio_signature

logger = logging.getLogger("asa.voice.twilio")


@dataclass(slots=True)
class VoiceTwilioSettings:
    account_sid: str
    auth_token: str
    from_number: str
    validate_signature: bool = True
    say_voice: str = "Polly.Joanna"
    barge_in: bool = True
    gather_timeout: int = 5
    speech_timeout: str = "auto"


class VoiceProviderPort(Protocol):
    def verify_webhook(
        self,
        *,
        url: str,
        params: dict[str, str],
        signature: str | None,
        alt_urls: list[str] | None = None,
    ) -> bool: ...

    def build_answer_twiml(
        self,
        *,
        say_text: str,
        action_url: str,
        stream_ws_url: str | None = None,
        record: bool = True,
    ) -> str: ...

    def build_gather_twiml(
        self,
        *,
        say_text: str,
        action_url: str,
        barge_in: bool = True,
    ) -> str: ...

    def build_redirect_twiml(self, *, url: str) -> str: ...

    def build_hangup_twiml(self, *, say_text: str | None = None) -> str: ...

    def build_dial_human_twiml(self, *, say_text: str, client_identity: str = "shop") -> str: ...


class FakeVoiceProvider:
    def __init__(self, settings: VoiceTwilioSettings | None = None) -> None:
        self.settings = settings or VoiceTwilioSettings(
            account_sid="ACfake",
            auth_token="fake",
            from_number="+15550001111",
            validate_signature=False,
        )
        self.twimls: list[str] = []

    def verify_webhook(
        self,
        *,
        url: str,
        params: dict[str, str],
        signature: str | None,
        alt_urls: list[str] | None = None,
    ) -> bool:
        return True

    def build_answer_twiml(
        self,
        *,
        say_text: str,
        action_url: str,
        stream_ws_url: str | None = None,
        record: bool = True,
    ) -> str:
        xml = render_answer_twiml(
            say_text=say_text,
            action_url=action_url,
            voice=self.settings.say_voice,
            barge_in=self.settings.barge_in,
            gather_timeout=self.settings.gather_timeout,
            speech_timeout=self.settings.speech_timeout,
            stream_ws_url=stream_ws_url,
            record=record,
        )
        self.twimls.append(xml)
        return xml

    def build_gather_twiml(self, *, say_text: str, action_url: str, barge_in: bool = True) -> str:
        xml = render_gather_twiml(
            say_text=say_text,
            action_url=action_url,
            voice=self.settings.say_voice,
            barge_in=barge_in,
            gather_timeout=self.settings.gather_timeout,
            speech_timeout=self.settings.speech_timeout,
        )
        self.twimls.append(xml)
        return xml

    def build_redirect_twiml(self, *, url: str) -> str:
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Redirect>{escape(url)}</Redirect></Response>'

    def build_hangup_twiml(self, *, say_text: str | None = None) -> str:
        say = f"<Say voice=\"{escape(self.settings.say_voice)}\">{escape(say_text)}</Say>" if say_text else ""
        return f'<?xml version="1.0" encoding="UTF-8"?><Response>{say}<Hangup/></Response>'

    def build_dial_human_twiml(self, *, say_text: str, client_identity: str = "shop") -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f'<Say voice="{escape(self.settings.say_voice)}">{escape(say_text)}</Say>'
            f"<Dial><Client>{escape(client_identity)}</Client></Dial>"
            "</Response>"
        )


class TwilioVoiceProvider:
    def __init__(self, settings: VoiceTwilioSettings) -> None:
        self.settings = settings

    def verify_webhook(
        self,
        *,
        url: str,
        params: dict[str, str],
        signature: str | None,
        alt_urls: list[str] | None = None,
    ) -> bool:
        if not self.settings.validate_signature:
            return True
        if not signature:
            return False
        return validate_twilio_signature(
            auth_token=self.settings.auth_token,
            url=url,
            params=params,
            signature=signature,
            alt_urls=alt_urls,
        )

    def build_answer_twiml(
        self,
        *,
        say_text: str,
        action_url: str,
        stream_ws_url: str | None = None,
        record: bool = True,
    ) -> str:
        return render_answer_twiml(
            say_text=say_text,
            action_url=action_url,
            voice=self.settings.say_voice,
            barge_in=self.settings.barge_in,
            gather_timeout=self.settings.gather_timeout,
            speech_timeout=self.settings.speech_timeout,
            stream_ws_url=stream_ws_url,
            record=record,
        )

    def build_gather_twiml(self, *, say_text: str, action_url: str, barge_in: bool = True) -> str:
        return render_gather_twiml(
            say_text=say_text,
            action_url=action_url,
            voice=self.settings.say_voice,
            barge_in=barge_in,
            gather_timeout=self.settings.gather_timeout,
            speech_timeout=self.settings.speech_timeout,
        )

    def build_redirect_twiml(self, *, url: str) -> str:
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Redirect>{escape(url)}</Redirect></Response>'

    def build_hangup_twiml(self, *, say_text: str | None = None) -> str:
        say = f"<Say voice=\"{escape(self.settings.say_voice)}\">{escape(say_text)}</Say>" if say_text else ""
        return f'<?xml version="1.0" encoding="UTF-8"?><Response>{say}<Hangup/></Response>'

    def build_dial_human_twiml(self, *, say_text: str, client_identity: str = "shop") -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f'<Say voice="{escape(self.settings.say_voice)}">{escape(say_text)}</Say>'
            f"<Dial><Client>{escape(client_identity)}</Client></Dial>"
            "</Response>"
        )


def render_gather_twiml(
    *,
    say_text: str,
    action_url: str,
    voice: str,
    barge_in: bool,
    gather_timeout: int,
    speech_timeout: str,
) -> str:
    barge = "true" if barge_in else "false"
    # Allow silent re-listen (empty silence timeout) without speaking.
    say = (
        f'<Say voice="{escape(voice)}">{escape(say_text)}</Say>'
        if (say_text or "").strip()
        else ""
    )
    # Prefer phone_call model; avoid enhanced=true (account/feature gated, can end Gather).
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Gather input="speech" action="{escape(action_url)}" method="POST" '
        f'timeout="{gather_timeout}" speechTimeout="{escape(speech_timeout)}" '
        f'speechModel="phone_call" language="en-US" '
        f'bargeIn="{barge}" actionOnEmptyResult="true">'
        f"{say}"
        "</Gather>"
        f'<Redirect method="POST">{escape(action_url)}</Redirect>'
        "</Response>"
    )


def render_answer_twiml(
    *,
    say_text: str,
    action_url: str,
    voice: str,
    barge_in: bool,
    gather_timeout: int,
    speech_timeout: str,
    stream_ws_url: str | None,
    record: bool,
) -> str:
    # NOTE: Do NOT emit a blocking <Record> here. Twilio docs: any verbs after
    # <Record> are unreachable, and missing action re-requests this URL → silent loop.
    # Enable call recording via Console / REST Call Recordings instead (see record flag).
    _ = record  # reserved for future dual-channel / REST recording start
    parts = ['<?xml version="1.0" encoding="UTF-8"?><Response>']
    if stream_ws_url:
        parts.append(
            f'<Start><Stream url="{escape(stream_ws_url)}" track="inbound_track" /></Start>'
        )
    barge = "true" if barge_in else "false"
    parts.append(
        f'<Gather input="speech" action="{escape(action_url)}" method="POST" '
        f'timeout="{gather_timeout}" speechTimeout="{escape(speech_timeout)}" '
        f'speechModel="phone_call" language="en-US" '
        f'bargeIn="{barge}" actionOnEmptyResult="true">'
        f'<Say voice="{escape(voice)}">{escape(say_text)}</Say>'
        "</Gather>"
    )
    parts.append(f'<Redirect method="POST">{escape(action_url)}</Redirect>')
    parts.append("</Response>")
    return "".join(parts)


def xml_response(content: str) -> str:
    # Convenience for tests; content already XML
    return content if content.startswith("<?xml") else f'<?xml version="1.0" encoding="UTF-8"?>{content}'


# silence unused html import warning by using escape from sax
_ = html
