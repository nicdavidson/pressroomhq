import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
import enum

from database import Base


class SignalType(str, enum.Enum):
    github_release = "github_release"
    github_commit = "github_commit"
    hackernews = "hackernews"
    reddit = "reddit"
    rss = "rss"
    trend = "trend"
    support = "support"
    performance = "performance"


class ContentChannel(str, enum.Enum):
    linkedin = "linkedin"
    x_thread = "x_thread"
    facebook = "facebook"
    blog = "blog"
    release_email = "release_email"
    newsletter = "newsletter"
    yt_script = "yt_script"


class ContentStatus(str, enum.Enum):
    generating = "generating"
    queued = "queued"
    approved = "approved"
    spiked = "spiked"
    published = "published"


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(SAEnum(SignalType), nullable=False)
    source = Column(String(255), nullable=False)
    title = Column(String(500), nullable=False)
    body = Column(Text, default="")
    url = Column(String(1000), default="")
    raw_data = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    contents = relationship("Content", back_populates="signal")


class Brief(Base):
    __tablename__ = "briefs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False)
    summary = Column(Text, nullable=False)
    angle = Column(String(500), default="")
    signal_ids = Column(Text, default="")  # comma-separated
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    contents = relationship("Content", back_populates="brief")


class Content(Base):
    __tablename__ = "content"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=True)
    brief_id = Column(Integer, ForeignKey("briefs.id"), nullable=True)
    channel = Column(SAEnum(ContentChannel), nullable=False)
    status = Column(SAEnum(ContentStatus), default=ContentStatus.queued)
    headline = Column(String(500), default="")
    body = Column(Text, nullable=False)
    body_raw = Column(Text, default="")  # pre-humanizer
    author = Column(String(100), default="company")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)

    signal = relationship("Signal", back_populates="contents")
    brief = relationship("Brief", back_populates="contents")
