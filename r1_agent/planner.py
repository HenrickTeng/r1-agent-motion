from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib import error, request

from r1_agent.catalog import ROOT, Action, Catalog, load_catalog


def load_deepseek_key(path: Path | None = None) -> str:
    env = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if env:
        return env
    key_path = path or ROOT / "deepseek_key.txt"
    try:
        return key_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _speech_action(catalog: Catalog, key: str) -> Action:
    text = catalog.speech[key]
    return Action(name=f"say:{key}", title=text, kind="speech", args={"text": text})


def _expand(catalog: Catalog, name: str) -> Action:
    if name.startswith("say:"):
        return _speech_action(catalog, name.split(":", 1)[1])
    return catalog.actions[name]


class RulePlanner:
    def __init__(self, catalog: Catalog | None = None) -> None:
        self.catalog = catalog or load_catalog()
        self.forbidden = re.compile("|".join(map(re.escape, self.catalog.forbidden)))

    def plan(self, text: str) -> tuple[str, list[Action]]:
        compact = re.sub(r"\s+", "", text)
        if self.forbidden.search(compact):
            return "这个动作不在当前安全动作库中，我不会执行。", []
        candidates: list[tuple[int, int, list[Action]]] = []
        for phrase, name in self.catalog.aliases:
            start = compact.find(phrase)
            if start >= 0:
                candidates.append((start, len(phrase), [_expand(self.catalog, name)]))
        for phrase, steps in self.catalog.compositions.items():
            start = compact.find(phrase)
            if start >= 0:
                candidates.append((start, len(phrase), [_expand(self.catalog, step) for step in steps]))
        occupied = [False] * len(compact)
        found: list[Action] = []
        for start, length, group in sorted(candidates, key=lambda item: (item[0], -item[1])):
            if any(occupied[start:start + length]):
                continue
            occupied[start:start + length] = [True] * length
            for action in group:
                if action not in found:
                    found.append(action)
        if not found:
            return "我目前能执行挥手、敬礼、鼓掌、点头、举手、缓慢移动和十度转向。", []
        return "好的，我会按顺序执行：" + "、".join(action.title for action in found), found


class DeepSeekPlanner:
    def __init__(
        self,
        catalog: Catalog | None = None,
        *,
        api_url: str = "https://api.deepseek.com/chat/completions",
        model: str = "deepseek-chat",
        timeout_s: float = 20,
    ) -> None:
        self.catalog = catalog or load_catalog()
        self.api_url = api_url
        self.model = model
        self.timeout_s = timeout_s
        self.fallback = RulePlanner(self.catalog)
        self._turns: list[dict[str, str]] = []

    def plan(self, text: str) -> tuple[str, list[Action]]:
        api_key = load_deepseek_key()
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set")
        names = [
            {"name": action.name, "title": action.title, "kind": action.kind}
            for action in self.catalog.actions.values()
        ]
        forbidden = "、".join(self.catalog.forbidden)
        system = (
            "你是 Unitree R1 的动作规划器。任务是把用户的任意指示（具体口令、角色、情境或对话）"
            "编排成目录里已有原子动作的有序序列，不要为某个场景写死套路。"
            "只输出 JSON：reply 是机器人要对面前的人说的中文，actions 是原子动作名数组。"
            f"只能使用这些原子动作名：{json.dumps(names, ensure_ascii=False)}。"
            "按语义选择、排序和重复这些原子动作；需要几步就用几步，但不要无意义拉长。"
            "同一套原子动作要能服务不同任务，不要假设用户总是在迎宾或上课。"
            "上肢和行走必须串行：先走再挥手，或先挥手再走，不要假设能边走边做手势。"
            f"不要规划 {forbidden}，也不要发明关节角、DDS、LowCmd、代码或目录外动作名。"
            "目录覆盖不了的要求：actions 为空，并在 reply 说明做不到。"
            "记住对话上下文，以便后续指示在已设定的角色或任务上继续组合。"
        )
        messages = [{"role": "system", "content": system}, *self._turns, {"role": "user", "content": text}]
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 800,
        }).encode()
        req = request.Request(
            self.api_url,
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_s) as response:
                envelope = json.loads(response.read())
            payload = json.loads(envelope["choices"][0]["message"]["content"])
        except (error.URLError, TimeoutError, KeyError, json.JSONDecodeError, IndexError, TypeError):
            return self.fallback.plan(text)
        names_in_plan = payload.get("actions") or []
        if not isinstance(names_in_plan, list):
            return self.fallback.plan(text)
        actions: list[Action] = []
        for name in names_in_plan:
            if not isinstance(name, str) or name not in self.catalog.actions:
                return "这个动作不在当前安全动作库中，我不会执行。", []
            actions.append(self.catalog.actions[name])
        reply = payload.get("reply")
        if not isinstance(reply, str) or not reply.strip():
            reply = "好的，我会按顺序执行：" + "、".join(action.title for action in actions) if actions else "我听到了。"
        self._turns.extend([
            {"role": "user", "content": text},
            {"role": "assistant", "content": json.dumps({"reply": reply, "actions": names_in_plan}, ensure_ascii=False)},
        ])
        self._turns = self._turns[-8:]
        return reply, actions
