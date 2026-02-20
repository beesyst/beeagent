from dataclasses import dataclass


@dataclass(frozen=True)
class Store:
    store_id: str
    name: str


@dataclass(frozen=True)
class SKU:
    sku_id: str
    name: str
    category: str
    price: float
    margin: float


@dataclass(frozen=True)
class SalesRow:
    date: str
    store_id: str
    sku_id: str
    units: int


@dataclass(frozen=True)
class StockRow:
    date: str
    store_id: str
    sku_id: str
    stock_on_hand: int


@dataclass(frozen=True)
class ShelfSignal:
    date: str
    store_id: str
    sku_id: str
    seen_on_shelf: bool


@dataclass(frozen=True)
class Alert:
    store_id: str
    sku_id: str
    rule_id: str
    severity: str
    details: str


@dataclass(frozen=True)
class Task:
    task_id: str
    store_id: str
    sku_id: str
    action: str
    status: str = "draft"


@dataclass(frozen=True)
class RunMeta:
    run_id: str
    created_at: str
    dataset_id: str
    seed: int


@dataclass(frozen=True)
class QuizAnswer:
    q_id: str
    question: str
    selected_answer_idx: int
    correct_answer_idx: int
    is_correct: bool


@dataclass(frozen=True)
class QuizResult:
    run_id: str
    quiz_id: str
    chat_id: int
    total_questions: int
    correct_answers: int
    score_percent: float
    created_at: str
