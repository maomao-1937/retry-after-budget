# Research

RFC 9110 defines `Retry-After` as either HTTP-date or an unsigned decimal delay measured in seconds. Its canonical sender form is IMF-fixdate, whose year semantics come from RFC 5322. The audit caps numeric hints and waiting budgets as part of its fixture profile. [RFC 9110 §10.2.3](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after), [RFC 9110 §5.6.7](https://www.rfc-editor.org/rfc/rfc9110.html#name-date-time-formats), [RFC 5322 §3.3](https://www.rfc-editor.org/rfc/rfc5322.html#section-3.3)

A DeerFlow issue reports that a zone-less legacy `asctime` hint was interpreted as local time, shifting a replayed delay on a non-UTC host. The report motivates an explicit UTC observation and a fixed interpretation in offline checks. This audit covers canonical date hints and decimal seconds. [DeerFlow issue 6604](https://github.com/bytedance/deer-flow/issues/6604)
