"""Fake LLM for agent tests: returns scripted structured outputs."""


class FakeStructured:
    def __init__(self, fake: "FakeLLM", schema):
        self.fake = fake
        self.schema = schema

    def invoke(self, prompt):
        self.fake.prompts.append((self.schema, prompt))
        return self.fake._next(self.schema)


class FakeLLM:
    """Mimics a chat model with ``.with_structured_output(Schema)``.

    ``responses`` maps a schema class to either a list of instances (popped in
    order) or a zero-arg callable that returns an instance.
    """

    def __init__(self, responses: dict | None = None):
        self._responses = responses or {}
        self.calls: list[tuple] = []
        self.prompts: list[tuple] = []

    def with_structured_output(self, schema):
        return FakeStructured(self, schema)

    def _next(self, schema):
        self.calls.append(schema)
        entry = self._responses.get(schema)
        if callable(entry):
            return entry()
        if isinstance(entry, list) and entry:
            return entry.pop(0)
        raise AssertionError(f"No scripted response for schema {schema!r}")


class FakeLLMFactory:
    def __init__(self, llm: FakeLLM):
        self.llm = llm

    def __call__(self) -> FakeLLM:
        return self.llm
