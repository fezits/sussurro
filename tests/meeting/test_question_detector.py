import numpy as np

from meeting.intelligence.question_detector import QuestionDetector


def test_detects_explicit_question():
    qd = QuestionDetector()
    assert qd.is_question("qual sua experiência com python?", audio_tail=None)


def test_detects_keyword_without_punctuation():
    qd = QuestionDetector()
    assert qd.is_question("me conta um pouco sobre você", audio_tail=None)


def test_rejects_statement():
    qd = QuestionDetector()
    assert not qd.is_question("entendi tudo certo aqui", audio_tail=None)


def test_prosody_pushes_borderline_to_question():
    qd = QuestionDetector()
    tail = np.concatenate([
        np.ones(int(0.3 * 16000), dtype=np.float32) * 0.05,  # quiet body
        np.ones(int(0.3 * 16000), dtype=np.float32) * 0.4,   # loud tail
    ])
    # Statement with no question marks/keywords but rising tail → still false
    assert not qd.is_question("sim certo", audio_tail=tail)
    # Statement with one keyword + rising tail → true (2 of 3)
    assert qd.is_question("você consegue isso", audio_tail=tail)
