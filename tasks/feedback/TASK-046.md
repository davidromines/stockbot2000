Round 1 (DeepSeek): security model implemented correctly (owner-only, fail closed,
stale check, two-step confirmations, offset persisted per update, no order commands).
Two defects fixed by Claude: /positions iterated the {slot: position} dict's KEYS (the
test had stubbed a list, so it passed); and exceptions from requests were printed with
the request URL, which contains the bot token — now scrubbed. Tests added for both.
