import enum

from sqlalchemy import Enum as SAEnum


class MediaType(str, enum.Enum):
    audio = "audio"
    video = "video"


class MediaSource(str, enum.Enum):
    upload = "upload"
    import_ = "import"
    extracted = "extracted"
    trimmed = "trimmed"
    isolated = "isolated"
    mixed = "mixed"
    export = "export"


class TrackType(str, enum.Enum):
    dialogue = "dialogue"
    music = "music"
    sfx = "sfx"
    other = "other"


class JobType(str, enum.Enum):
    isolate = "isolate"
    mix = "mix"
    transcribe = "transcribe"
    export = "export"
    import_ = "import"


class JobStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


def str_enum(enum_cls: type[enum.Enum], name: str) -> SAEnum:
    """Store enum *values* as VARCHAR + CHECK constraint (easy to extend in migrations)."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda cls: [member.value for member in cls],
        validate_strings=True,
    )
