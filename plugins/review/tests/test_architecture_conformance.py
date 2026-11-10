from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parents[1] / "agents"
PERSONA = AGENTS_DIR / "architecture-conformance.agent.md"
RULE = (
    "A protocol, trait, or interface is introduced only at a boundary where the dependency is IO (process, network, filesystem, database, clock, randomness, hardware) or where a second real implementation exists. A test double counts as a second implementation only for IO. Pure in-process code with one implementation is called directly."
)


def _checklist_items(text: str) -> list[str]:
    section = text.split("## Checklist", 1)[1]
    return [line.strip() for line in section.splitlines() if line.strip()[:2] in {"1.", "2.", "3.", "4.", "5."}]


def test_persona_pins_the_earned_abstraction_rule():
    text = PERSONA.read_text(encoding="utf-8")
    assert RULE in text


def test_persona_checklist_has_exactly_five_items():
    text = PERSONA.read_text(encoding="utf-8")
    assert "## Checklist" in text
    assert [item[:2] for item in _checklist_items(text)] == ["1.", "2.", "3.", "4.", "5."]
