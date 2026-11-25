"""按完整表达决定 QQ 回复的气泡。"""
import re


CHAT_BUBBLES_MAX_CHARS = 120
FORWARD_AFTER_CHARS = 600
FORWARD_AFTER_LINES = 12
MAX_SEGMENTS = 3
STRUCTURED_TEXT = re.compile(r"```|~~~|(?m:^\s*(?:[-*+]\s|\d+[.)、]\s|[>#|]))")
PARAGRAPH_BREAK = re.compile(r"\r?\n(?:[ \t]*\r?\n)+")
CONTINUATION = re.compile(r"^(?:然后|结果|不过|所以|但是|而且|因为|也就是说)")
SENTENCE_BOUNDARY = re.compile(
    r'“[^”]*”|‘[^’]*’|「[^」]*」|『[^』]*』|"[^"\n]*"|`[^`\n]+`'
    r'|\b(?:Mr|Mrs|Ms|Dr|Prof|etc|e\.g|i\.e|vs)\.'
    r'|(?P<end>[。！？]+|[!?]+(?=\s|$)|\.(?=\s+[A-Z]|$))',
)


def should_fold(text: str) -> bool:
    return len(text) > FORWARD_AFTER_CHARS or len(text.splitlines()) > FORWARD_AFTER_LINES


def split_reply(text: str) -> tuple[str, ...]:
    text = text.strip()
    if len(text) > CHAT_BUBBLES_MAX_CHARS or STRUCTURED_TEXT.search(text):
        return (text,)

    boundaries = [match.span() for match in PARAGRAPH_BREAK.finditer(text)]
    if not boundaries:
        boundaries = [(match.end(), match.end()) for match in SENTENCE_BOUNDARY.finditer(text) if match.lastgroup == "end"]

    segments: list[str] = []
    start = 0
    for end, next_start in boundaries:
        following = text[next_start:].lstrip()
        if not following or CONTINUATION.match(following):
            continue
        segment = text[start:end].strip()
        if segment:
            segments.append(segment)
        if len(segments) == MAX_SEGMENTS:
            return (text,)
        start = next_start
    segments.append(text[start:].strip())
    return tuple(segments)
