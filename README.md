# Retry-After Budget

[![tests](https://github.com/maomao-1937/retry-after-budget/actions/workflows/tests.yml/badge.svg)](https://github.com/maomao-1937/retry-after-budget/actions/workflows/tests.yml)

Replay a saved HTTP `Retry-After` value against a fixed UTC observation and a waiting budget. The command reports the computed delay and whether it fits, so the same fixture gives the same answer regardless of when or where it runs.

## Quick start

Use Python 3.11 or later on Windows or Linux. From the repository root, run the bundled examples.

```sh
python retry_after_budget.py examples/delta-at-budget.json
python retry_after_budget.py examples/date-over-budget.json
python retry_after_budget.py examples/date-expired.json
python retry_after_budget.py examples/invalid-obsolete-date.json
```

The commands exit 0, 1, 0 and 2, respectively. The second example requests a 180-second wait with a budget of 60 seconds.

```json
{"status":"over_budget","form":"http_date","delay_seconds":180,"expired":false}
```

## Input and calculation

Use a regular local file of up to 256 KiB with a UTF-8 JSON object containing exactly these keys. A BOM and duplicate keys are invalid.

| Key | Accepted value |
| --- | --- |
| `retry_after` | A string of at most 128 Unicode code points. Outer ASCII space and tab are ignored. Use ASCII decimal digits with optional leading zeros and a value from 0 through 2147483647, or use exact IMF-fixdate with matching weekday and a year from 1900 through 9999. |
| `observed_at` | Exact UTC `YYYY-MM-DDTHH:MM:SSZ`, with a Gregorian year from 0001 through 9999 and no fractional seconds. |
| `max_delay_seconds` | A JSON integer from 0 through 2147483647. |

Both date inputs must have valid Gregorian dates and times. Leap seconds are outside this fixture format. Date hints produce the number of seconds from observation to the stated date, floored at zero. `expired` is true only when the stated date precedes the observation. Delta-seconds hints are already relative and always have `expired: false`. A delay equal to the budget fits. The report omits the original strings, budget and path.

This fixture format accepts the canonical sender date. RFC 9110 requires HTTP recipients parsing timestamp fields to accept IMF-fixdate and both obsolete HTTP-date forms. The CLI replays one saved value without contacting servers, waiting or retrying. [RFC 9110 §5.6.7](https://www.rfc-editor.org/rfc/rfc9110.html#name-date-time-formats), [RFC 9110 §10.2.3](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after)

| Exit | Report |
| --- | --- |
| 0 | `within_budget` for a valid delay within the inclusive budget. Help also exits 0. |
| 1 | `over_budget` for a valid delay greater than the budget. |
| 2 | `invalid` for bad arguments, invalid data or a read failure. Unavailable stdout exits 2 quietly. |

Use a trusted local directory. The CLI checks the supplied path spelling before opening the file. The filesystem resolves links and mounts.

## 中文

这个工具用固定 UTC 观测时间复现一条已保存的 `Retry-After`，给出等待秒数和预算判断。输出不包含原始字段值或文件路径。

在 Windows 或 Linux 使用 Python 3.11 或更新版本，按上方命令运行仓库里的四个示例。退出码依次为 0、1、0、2。第二个示例要求等待 180 秒，超出 60 秒预算。第三个示例的日期已经过去，等待时间为 0，`expired` 为 `true`。

输入是 256 KiB 以内的本地 UTF-8 JSON 文件，只包含 `retry_after`、`observed_at` 和 `max_delay_seconds`。`retry_after` 支持十进制秒数或严格的 IMF-fixdate 日期。`observed_at` 使用 UTC 的 `YYYY-MM-DDTHH:MM:SSZ`，预算是 0 至 2147483647 的整数。等待时间等于预算时仍通过。只有早于观测时刻的日期才标记过期。退出码 0 表示预算内，1 表示超预算，2 表示参数、输入或输出失败。

这是离线样本的格式。RFC 9110 要求解析 HTTP 时间戳的接收方接受两种旧日期格式和 IMF-fixdate。

See [research](RESEARCH.md) and [tests](TESTING.md). MIT licensed.
