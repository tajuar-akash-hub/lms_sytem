import enum


class LeagueTier(str, enum.Enum):
    IRON = "IRON"
    BRONZE = "BRONZE"
    SILVER = "SILVER"
    GOLD = "GOLD"
    PLATINUM = "PLATINUM"
    ASCENDANT = "ASCENDANT"
    IMMORTAL = "IMMORTAL"
    RADIANT = "RADIANT"


class ModuleType(str, enum.Enum):
    REGULAR = "REGULAR"
    EXAM = "EXAM"
    CONCEPTUAL = "CONCEPTUAL"
    GROWTH_DAY = "GROWTH_DAY"


class PairChallengeStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class LearningStatus(str, enum.Enum):
    WEAK = "WEAK"
    IMPROVING = "IMPROVING"
    RESOLVED = "RESOLVED"


class ExamType(str, enum.Enum):
    MCQ = "MCQ"
    CODING = "CODING"
    WRITTEN = "WRITTEN"
    MIXED = "MIXED"
