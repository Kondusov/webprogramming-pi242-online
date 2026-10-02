from __future__ import annotations
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, create_engine, select, Index,
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship,
    sessionmaker, Session,
)
from sqlalchemy.pool import StaticPool

from .config import settings


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    id:             Mapped[int]      = mapped_column(Integer, primary_key=True)
    username:       Mapped[str]      = mapped_column(String(32), unique=True, index=True)
    email:          Mapped[Optional[str]] = mapped_column(String(254), unique=True, index=True)
    password_hash:  Mapped[str]      = mapped_column(String(255))
    email_verified: Mapped[bool]     = mapped_column(Boolean, default=False)
    created_at:     Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EmailCode(Base):
    __tablename__ = "email_codes"
    id:         Mapped[int]      = mapped_column(Integer, primary_key=True)
    user_id:    Mapped[int]      = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code:       Mapped[str]      = mapped_column(String(6))
    purpose:    Mapped[str]      = mapped_column(String(16))   # verify | reset
    expires_at: Mapped[int]      = mapped_column(BigInteger)
    used:       Mapped[bool]     = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Chat(Base):
    __tablename__ = "chats"
    id:         Mapped[int]      = mapped_column(Integer, primary_key=True)
    type:       Mapped[str]      = mapped_column(String(16))   # group | channel | dm
    name:       Mapped[Optional[str]] = mapped_column(String(64))
    owner_id:   Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    members: Mapped[list["ChatMember"]] = relationship(back_populates="chat", cascade="all, delete-orphan")


class ChatMember(Base):
    __tablename__ = "chat_members"
    __table_args__ = (UniqueConstraint("chat_id", "user_id", name="uq_chat_user"),)
    id:        Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id:   Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    user_id:   Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role:      Mapped[str] = mapped_column(String(16), default="member")  # owner | member
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    chat: Mapped[Chat] = relationship(back_populates="members")


class Message(Base):
    __tablename__ = "messages"
    id:      Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    text:    Mapped[str] = mapped_column(Text)
    time:    Mapped[str] = mapped_column(String(16))
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class Reaction(Base):
    __tablename__ = "reactions"
    __table_args__ = (UniqueConstraint("message_id", "user_id", "emoji", name="uq_reaction"),)
    id:         Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    user_id:    Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    emoji:      Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DmPair(Base):
    __tablename__ = "dm_pairs"
    __table_args__ = (UniqueConstraint("user_a", "user_b", name="uq_dm_pair"),)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), primary_key=True)
    user_a:  Mapped[int] = mapped_column(Integer, index=True)
    user_b:  Mapped[int] = mapped_column(Integer, index=True)


# --- движок и фабрика сессий ---

engine = create_engine(
    f"sqlite:///{settings.DB_PATH}",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool if ":memory:" in str(settings.DB_PATH) else None,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def init_db() -> None:
    Base.metadata.create_all(engine)


def db_session() -> Session:
    """Возвращает новую сессию. Использовать в контекстном менеджере."""
    return SessionLocal()