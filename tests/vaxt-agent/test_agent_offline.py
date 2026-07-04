"""Agent-loop tests driven by a stub model — no API key, no warehouse.

These pin the loop's behavior (tool execution, submit_answer finalization,
refusal, unstructured fallback, usage accounting) deterministically.
"""

from vaxt_agent.agent import run_agent


class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _tool_use(name, tid, inp):
    return _Block(type="tool_use", name=name, id=tid, input=inp)


def _text(s):
    return _Block(type="text", text=s)


class _Resp:
    def __init__(self, content, usage=None):
        self.content = content
        self.usage = usage or {"input_tokens": 10, "output_tokens": 5}


class _Messages:
    def __init__(self, scripted):
        self._s = list(scripted)
        self._i = 0
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        r = self._s[self._i]
        self._i += 1
        return r


class StubClient:
    def __init__(self, scripted):
        self.messages = _Messages(scripted)


class FakeCore:
    def __init__(self, env):
        self.env = env
        self.calls = []
        self.closed = False

    def call(self, name, args):
        self.calls.append((name, dict(args)))
        return self.env

    def close(self):
        self.closed = True


def test_tool_then_submit_builds_grounded_transcript():
    env = {"tool": "vaxt_search_varieties", "count": 1,
           "records": [{"table": "varieties", "key": "Norstar", "key_column": "variety", "fields": {}}]}
    core = FakeCore(env)
    client = StubClient([
        _Resp([_tool_use("vaxt_search_varieties", "t1", {"crop": "wheat"})]),
        _Resp([_tool_use("submit_answer", "t2", {
            "answer": "Norstar is a winter wheat.",
            "claims": [{"text": "Norstar is a winter wheat.",
                        "citations": [{"table": "varieties", "key": "Norstar"}]}],
            "refused": False,
        })]),
    ])

    t = run_agent("tell me about Norstar", anthropic_client=client, toolcore=core)

    assert t.refused is False
    assert t.answer == "Norstar is a winter wheat."
    assert len(t.claims) == 1
    assert t.all_citations()[0].table == "varieties"
    assert t.all_citations()[0].key == "Norstar"
    assert [tc.tool for tc in t.tool_calls] == ["vaxt_search_varieties"]
    assert t.tool_calls[0].record_count == 1
    # usage accumulates across both model turns
    assert t.usage["input_tokens"] == 20
    assert t.usage["output_tokens"] == 10
    assert core.calls == [("vaxt_search_varieties", {"crop": "wheat"})]


def test_refusal_carries_no_citations():
    core = FakeCore({"records": [], "count": 0})
    client = StubClient([
        _Resp([_tool_use("submit_answer", "t1", {
            "answer": "I don't have market-price data.",
            "claims": [],
            "refused": True,
            "refusal_reason": "Out of scope: no price data in the warehouse.",
        })]),
    ])
    t = run_agent("price of wheat futures?", anthropic_client=client, toolcore=core)
    assert t.refused is True
    assert t.all_citations() == []
    assert "scope" in t.refusal_reason.lower()


def test_unstructured_finish_is_flagged():
    core = FakeCore({"records": [], "count": 0})
    client = StubClient([_Resp([_text("Here is a plain answer with no submit_answer call.")])])
    t = run_agent("hi", anthropic_client=client, toolcore=core)
    assert t.unstructured is True
    assert "plain answer" in t.answer
    assert t.claims == []
