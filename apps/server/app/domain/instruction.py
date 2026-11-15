"""对话指令解析（契约 §6.9）：把「第二天想吃清淡点，不要鸡蛋」这类自然语言
拆成结构化改动意图。

模型可用时优先用 LLM 的输出（`app/domain/preferences.py` 里统一合并），
模型不可用 / 输出不可用时用本模块的规则版兜底——两条路径产出的结构一致：

```python
{"days": [2], "slots": [], "avoid": ["鸡蛋"], "requested": [],
 "light": True, "swap_to": None, "note": "..."}
```

`days` 是 1-based 的下标（对应计划里的第几天），`slots` 为空表示当天所有餐次。
"""

from __future__ import annotations

import re
from typing import Any

SLOT_LUNCH = "午餐"
SLOT_DINNER = "晚餐"
SLOT_ALIASES: dict[str, tuple[str, ...]] = {
    SLOT_LUNCH: ("午餐", "中午", "午饭", "中饭"),
    SLOT_DINNER: ("晚餐", "晚上", "晚饭"),
}

DAY_CHARS: dict[str, int] = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7}
RELATIVE_DAYS: dict[str, int] = {"明天": 1, "后天": 2, "大后天": 3}
DAY_PATTERN = re.compile(r"第\s*([1-9一二三四五六七])\s*天")
MAX_DAY_INDEX = 7

LIGHT_WORDS: tuple[str, ...] = (
    "清淡",
    "少油",
    "少盐",
    "清蒸",
    "轻食",
    "减脂",
    "素一点",
    "爽口",
    "不油腻",
    "别太油",
)
NEGATIVE_VERBS: tuple[str, ...] = (
    "不要",
    "不吃",
    "别放",
    "不放",
    "别吃",
    "去掉",
    "不加",
    "不想吃",
    "不能吃",
    "忌",
    "戒",
)
POSITIVE_VERBS: tuple[str, ...] = ("想吃", "来点", "加点", "要吃", "多加", "多吃")
SWAP_PATTERN = re.compile(r"(?:换成|改成|改吃|换成吃|吃点)\s*([\u4e00-\u9fa5A-Za-z0-9]{2,10})")

_VERB_GROUP = "|".join(re.escape(verb) for verb in NEGATIVE_VERBS)
_POSITIVE_GROUP = "|".join(re.escape(verb) for verb in POSITIVE_VERBS)
FILLER = r"(?:放|吃|用|再|加|做|点)?"


def _day_value(raw: str) -> int | None:
    if raw.isdigit():
        return int(raw)
    return DAY_CHARS.get(raw)


def parse_days(instruction: str) -> list[int]:
    """「第二天」「第3天」「明天」→ 1-based 天下标（去重升序）。"""
    text = str(instruction or "")
    days: list[int] = []
    for match in DAY_PATTERN.finditer(text):
        value = _day_value(match.group(1))
        if value and 1 <= value <= MAX_DAY_INDEX and value not in days:
            days.append(value)
    used_spans: list[tuple[int, int]] = []
    for word in sorted(RELATIVE_DAYS, key=len, reverse=True):
        start = text.find(word)
        if start < 0:
            continue
        span = (start, start + len(word))
        if any(start >= left and span[1] <= right for left, right in used_spans):
            continue  # 「大后天」已经算过，不再重复算「后天」
        used_spans.append(span)
        value = RELATIVE_DAYS[word]
        if value not in days:
            days.append(value)
    return sorted(days)


def parse_slots(instruction: str) -> list[str]:
    text = str(instruction or "")
    slots: list[str] = []
    for slot, aliases in SLOT_ALIASES.items():
        if any(alias in text for alias in aliases) and slot not in slots:
            slots.append(slot)
    return slots


def mentions_light(instruction: str) -> bool:
    text = str(instruction or "")
    return any(word in text for word in LIGHT_WORDS)


def _negated(name: str, text: str) -> bool:
    prefix = re.search(rf"(?:{_VERB_GROUP}){FILLER}\s*{re.escape(name)}", text)
    suffix = re.search(rf"{re.escape(name)}\s*(?:{_VERB_GROUP})", text)
    return bool(prefix or suffix)


def _requested(name: str, text: str) -> bool:
    return bool(re.search(rf"(?:{_POSITIVE_GROUP})\s*{re.escape(name)}", text))


def names_negated(instruction: str, vocabulary: list[str]) -> list[str]:
    """指令里被明确否掉的食材（只认词表里的名字，避免把整句当食材）。"""
    text = str(instruction or "")
    return [name for name in _dedup_vocabulary(vocabulary) if _negated(name, text)]


def names_requested(instruction: str, vocabulary: list[str]) -> list[str]:
    text = str(instruction or "")
    return [name for name in _dedup_vocabulary(vocabulary) if _requested(name, text)]


def _dedup_vocabulary(vocabulary: list[str]) -> list[str]:
    names = [str(name).strip() for name in vocabulary if str(name or "").strip()]
    # 长名优先：先匹配「西兰花」再匹配「西兰」，避免命中半截
    return sorted(dict.fromkeys(names), key=len, reverse=True)


def parse_swap_target(instruction: str) -> str | None:
    match = SWAP_PATTERN.search(str(instruction or ""))
    return match.group(1).strip() if match else None


def parse_instruction(instruction: str, vocabulary: list[str]) -> dict:
    """规则版解析（模型不可用时的兜底，也是 LLM 输出的交叉校验）。"""
    text = str(instruction or "").strip()
    avoid = names_negated(text, vocabulary)
    requested = [name for name in names_requested(text, vocabulary) if name not in avoid]
    return {
        "days": parse_days(text),
        "slots": parse_slots(text),
        "avoid": avoid,
        "requested": requested,
        "light": mentions_light(text),
        "swap_to": parse_swap_target(text),
        "note": text[:60],
    }


def merge_intents(rule: dict, llm: Any) -> dict:
    """规则版为主、LLM 补充（模型常漏掉中文否定词，规则版兜底更可靠）。"""
    merged = dict(rule)
    if not isinstance(llm, dict):
        return merged

    days = [int(day) for day in _as_list(llm.get("days")) if str(day).isdigit()]
    days = [day for day in days if 1 <= day <= MAX_DAY_INDEX]
    if days:
        merged["days"] = sorted(dict.fromkeys([*merged["days"], *days]))

    slots = [str(slot).strip() for slot in _as_list(llm.get("slots"))]
    slots = [slot for slot in slots if slot in SLOT_ALIASES]
    if slots:
        merged["slots"] = list(dict.fromkeys([*merged["slots"], *slots]))

    avoid = [str(name).strip() for name in _as_list(llm.get("avoid"))]
    merged["avoid"] = list(dict.fromkeys([*merged["avoid"], *[name for name in avoid if name]]))

    requested = [str(name).strip() for name in _as_list(llm.get("requested"))]
    requested = [name for name in requested if name and name not in merged["avoid"]]
    merged["requested"] = list(dict.fromkeys([*merged["requested"], *requested]))

    if bool(llm.get("light")):
        merged["light"] = True

    swap_to = str(llm.get("swap_to") or "").strip()
    if swap_to and not merged.get("swap_to"):
        merged["swap_to"] = swap_to
    return merged


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value in (None, "", []):
        return []
    return [value]
