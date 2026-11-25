"""只在长回复的自然停顿处分段。"""
import re


SHORT_REPLY_LENGTH = 80
MIN_SEGMENT_LENGTH = 36
MAX_SEGMENTS = 3
STRUCTURED_TEXT = re.compile(r"```|~~~|(?m:^\s*(?:[-*+]\s|\d+[.)、]\s|[>#|]))")
PARAGRAPH_BREAK = re.compile(r"\r?\n(?:[ \t]*\r?\n)+")
SENTENCE_BOUNDARY = re.compile(
    r'“[^”]*”|‘[^’]*’|「[^」]*」|『[^』]*』|"[^"\n]*"|`[^`\n]+`'
    r'|\b(?:Mr|Mrs|Ms|Dr|Prof|etc|e\.g|i\.e|vs)\.'
    r'|(?P<end>[。！？]+|[!?]+(?=\s|$)|\.(?=\s+[A-Z]|$))',
)


def split_reply(text: str) -> tuple[str, ...]:
    text = text.strip()
    if len(text) <= SHORT_REPLY_LENGTH or STRUCTURED_TEXT.search(text):
        return (text,)

    boundaries = [match.span() for match in PARAGRAPH_BREAK.finditer(text)]
    if not boundaries:
        boundaries = [(match.end(), match.end()) for match in SENTENCE_BOUNDARY.finditer(text) if match.lastgroup == "end"]

    segments: list[str] = []
    start = 0
    for end, next_start in boundaries:
        if len(text[next_start:].lstrip()) < MIN_SEGMENT_LENGTH:
            break
        segment = text[start:end].strip()
        if len(segment) < MIN_SEGMENT_LENGTH:
            continue
        segments.append(segment)
        start = next_start
        if len(segments) == MAX_SEGMENTS - 1:
            break
    segments.append(text[start:].strip())
    return tuple(segments)
