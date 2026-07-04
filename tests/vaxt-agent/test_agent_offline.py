"""Agent-loop tests driven by a stub model — no API key, no warehouse.

These pin the loop: run data tools, then parse inline [table:key] citations and
the [[REFUSED]] token out of the model's prose answer.
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
    def __init__(self, env=None):
        self.env = env or {"records": [], "count": 0}
        self.calls = []
        self.closed = False

    def call(self, name, args):
        self.calls.append((name, dict(args)))
        return self.env

    def close(self):
        self.closed = True


def test_tool_then_prose_answer_is_parsed():
    core = FakeCore()
    client = StubClient([
        _Resp([_tool_use("vaxt_get_variety", "t1", {"name": "Norstar"})]),
        _Resp([_text("Norstar is a winter wheat [varieties:Norstar]. "
                     "It tolerates pink snow mould [disease_resistance:Norstar].")]),
    ])
    t = run_agent("about Norstar", anthropic_client=client, toolcore=core)

    assert t.refused is False
    assert {(c.table, c.key) for c in t.all_citations()} == {
        ("varieties", "Norstar"), ("disease_resistance", "Norstar")
    }
    assert [tc.tool for tc in t.tool_calls] == ["vaxt_get_variety"]
    assert len(t.claims) == 2                      # two cited sentences
    assert "[varieties:Norstar]" not in t.answer   # tags stripped for display
    assert core.calls == [("vaxt_get_variety", {"name": "Norstar"})]


def test_refusal_token_is_detected():
    core = FakeCore()
    client = StubClient([_Resp([_text("I don't have market-price data. [[REFUSED]]")])])
    t = run_agent("price of wheat futures?", anthropic_client=client, toolcore=core)
    assert t.refused is True
    assert t.all_citations() == []
    assert "REFUSED" not in t.answer               # token stripped from display
    assert "market-price" in t.refusal_reason


def test_answerable_without_citations_yields_none():
    core = FakeCore()
    client = StubClient([_Resp([_text("Some prose with no citations at all.")])])
    t = run_agent("hi", anthropic_client=client, toolcore=core)
    assert t.refused is False
    assert t.all_citations() == []                 # grader fails this (no citations)


def test_usage_accumulates_across_turns():
    core = FakeCore()
    client = StubClient([
        _Resp([_tool_use("vaxt_search_varieties", "t1", {"crop": "wheat"})]),
        _Resp([_text("Wheat varieties are present [varieties:Norstar].")]),
    ])
    t = run_agent("q", anthropic_client=client, toolcore=core)
    assert t.usage["input_tokens"] == 20
    assert t.usage["output_tokens"] == 10
