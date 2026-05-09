from meeting.intelligence.classifier import Classifier
from meeting.intelligence.types import SuggestionKind


class _StubLlm:
    def __init__(self, answer: str): self.answer = answer
    def complete(self, messages): return self.answer


def test_classifier_returns_personal():
    c = Classifier(llm=_StubLlm("A"), model="x")
    assert c.classify("conta sobre sua experiência", "") is SuggestionKind.PERSONAL


def test_classifier_returns_technical():
    c = Classifier(llm=_StubLlm("B"), model="x")
    assert c.classify("como funciona OAuth", "") is SuggestionKind.TECHNICAL


def test_classifier_returns_hybrid_for_unclear():
    c = Classifier(llm=_StubLlm("C"), model="x")
    assert c.classify("...", "") is SuggestionKind.HYBRID


def test_classifier_defaults_to_hybrid_on_garbage():
    c = Classifier(llm=_StubLlm("???"), model="x")
    assert c.classify("...", "") is SuggestionKind.HYBRID
