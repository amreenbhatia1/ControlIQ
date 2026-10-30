from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class Message(BaseModel):
    message: str


class UserRef(ORMModel):
    id: int
    full_name: str
    email: str
    title: str = ""


class Timestamped(BaseModel):
    created_at: datetime | None = None
