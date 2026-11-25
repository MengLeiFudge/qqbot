"""按自然段和完整句子切分 QQ 文本回复。"""
import re


SHORT_REPLY_LENGTH = 36
MIN_SEGMENT_LENGTH = 12
MAX_SEGMENTS = 3
STRUCTURED_TEXT = re.compile(r"```|~~~|(?m:^\s*(?:[-*+]\s|\d+[.)、]\s|[>#|]))")
SENTENCE_BOUNDARY = re.compile(
    r'“[^”]*”|‘[^’]*’|「[^」]*」|『[^』]*』|"[^"\n]*"|`[^`\n]+`'
    r'|\b(?:Mr|Mrs|Ms|Dr|Prof|etc|e\.g|i\.e|vs)\.'
    r'|(?P<end>[。！？]+|[!?]+(?=\s|$)|\.(?=\s+[A-Z]|$))',
)


def split_reply(text: str) -> tuple[str, ...]:
    text = text.strip()
    if len(text) <= SHORT_REPLY_LENGTH or STRUCTURED_TEXT.search(text):
        return (text,)

    paragraphs = [part.strip() for part in re.split(r"\r?\n(?:[ \t]*\r?\n)+", text) if part.strip()]
    if len(paragraphs) > 1:
        units = paragraphs
        separator = "\n\n"
    else:
        units = []
        separator = ""
        start = 0
        for match in SENTENCE_BOUNDARY.finditer(text):
            if match.lastgroup == "end" and match.end() - start >= MIN_SEGMENT_LENGTH:
                units.append(text[start:match.end()])
                start = match.end()
        if text[start:].strip():
            units.append(text[start:])

    segments: list[str] = []
    buffer = ""
    for unit in units:
        buffer = f"{buffer}{separator}{unit}" if buffer else unit
        if len(buffer.strip()) >= MIN_SEGMENT_LENGTH and len(segments) < MAX_SEGMENTS - 1:
            segments.append(buffer)
            buffer = ""
    if buffer.strip():
        if segments and len(buffer.strip()) < MIN_SEGMENT_LENGTH:
            segments[-1] += separator + buffer
        else:
            segments.append(buffer)
    return tuple(segment.strip() for segment in segments) or (text,)
