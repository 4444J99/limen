from pydantic import BaseModel, field_validator


class Base(BaseModel):
    @field_validator("name", "age", check_fields=False)
    @classmethod
    def reject_bad(cls, value: str | None) -> str | None:
        if value == "bad":
            raise ValueError("bad")
        return value


class ChildWithName(Base):
    name: str


class ChildWithAge(Base):
    age: str


def test_base_validator_applies_to_child_field_name() -> None:
    assert ChildWithName(name="good").name == "good"

    try:
        ChildWithName(name="bad")
    except ValueError as exc:
        assert "bad" in str(exc)
    else:
        raise AssertionError("expected inherited validator to reject bad name")


def test_base_validator_applies_to_child_field_age() -> None:
    assert ChildWithAge(age="good").age == "good"

    try:
        ChildWithAge(age="bad")
    except ValueError as exc:
        assert "bad" in str(exc)
    else:
        raise AssertionError("expected inherited validator to reject bad age")
