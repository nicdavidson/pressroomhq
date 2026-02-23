import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SAEnum, UniqueConstraint
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


class StoryStatus(str, enum.Enum):
    draft = "draft"
    generating = "generating"
    complete = "complete"


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    domain = Column(String(500), default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    signals = relationship("Signal", back_populates="org", cascade="all, delete-orphan")
    briefs = relationship("Brief", back_populates="org", cascade="all, delete-orphan")
    contents = relationship("Content", back_populates="org", cascade="all, delete-orphan")
    settings = relationship("Setting", back_populates="org", cascade="all, delete-orphan")
    data_sources = relationship("DataSource", back_populates="org", cascade="all, delete-orphan")
    assets = relationship("CompanyAsset", back_populates="org", cascade="all, delete-orphan")
    stories = relationship("Story", back_populates="org", cascade="all, delete-orphan")


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    type = Column(SAEnum(SignalType), nullable=False)
    source = Column(String(255), nullable=False)
    title = Column(String(500), nullable=False)
    body = Column(Text, default="")
    url = Column(String(1000), default="")
    raw_data = Column(Text, default="")
    prioritized = Column(Integer, default=0)  # 1 = editor-prioritized for content gen
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    org = relationship("Organization", back_populates="signals")
    contents = relationship("Content", back_populates="signal")


class Brief(Base):
    __tablename__ = "briefs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    date = Column(String(10), nullable=False)
    summary = Column(Text, nullable=False)
    angle = Column(String(500), default="")
    signal_ids = Column(Text, default="")  # comma-separated
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    org = relationship("Organization", back_populates="briefs")
    contents = relationship("Content", back_populates="brief")


class Content(Base):
    __tablename__ = "content"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=True)
    brief_id = Column(Integer, ForeignKey("briefs.id"), nullable=True)
    story_id = Column(Integer, ForeignKey("stories.id"), nullable=True)
    channel = Column(SAEnum(ContentChannel), nullable=False)
    status = Column(SAEnum(ContentStatus), default=ContentStatus.queued)
    headline = Column(String(500), default="")
    body = Column(Text, nullable=False)
    body_raw = Column(Text, default="")  # pre-humanizer
    author = Column(String(100), default="company")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)

    org = relationship("Organization", back_populates="contents")
    signal = relationship("Signal", back_populates="contents")
    brief = relationship("Brief", back_populates="contents")
    story = relationship("Story", back_populates="contents")


class DataSource(Base):
    """External data connection — DreamFactory instance, database, API, etc."""
    __tablename__ = "data_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    name = Column(String(255), nullable=False)         # e.g. "Intercom Data"
    description = Column(Text, default="")              # what this source contains
    category = Column(String(100), default="database")  # database, crm, analytics, support, custom
    connection_type = Column(String(50), default="mcp")  # mcp, rest_api
    base_url = Column(String(1000), default="")         # e.g. http://df.example.com
    api_key = Column(String(500), default="")           # auth key
    config = Column(Text, default="{}")                 # extra JSON config
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    org = relationship("Organization", back_populates="data_sources")


class CompanyAsset(Base):
    """Discovered or manually added company digital asset."""
    __tablename__ = "company_assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    asset_type = Column(String(50), nullable=False)  # subdomain, blog, docs, repo, social, api_endpoint
    url = Column(String(1000), nullable=False)
    label = Column(String(255), default="")           # user-editable: "primary blog", "main docs"
    description = Column(String(1000), default="")
    discovered_via = Column(String(50), default="manual")  # onboarding, manual
    auto_discovered = Column(Integer, default=0)
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    org = relationship("Organization", back_populates="assets")


class Story(Base):
    """Editorial story — curated signals + angle for targeted content generation."""
    __tablename__ = "stories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    title = Column(String(500), nullable=False)
    angle = Column(Text, default="")
    editorial_notes = Column(Text, default="")
    status = Column(SAEnum(StoryStatus), default=StoryStatus.draft)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    org = relationship("Organization", back_populates="stories")
    story_signals = relationship("StorySignal", back_populates="story", cascade="all, delete-orphan")
    contents = relationship("Content", back_populates="story")


class StorySignal(Base):
    """Join table — links signals to stories with per-signal editorial notes."""
    __tablename__ = "story_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    story_id = Column(Integer, ForeignKey("stories.id"), nullable=False)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=False)
    editor_notes = Column(Text, default="")
    sort_order = Column(Integer, default=0)

    story = relationship("Story", back_populates="story_signals")
    signal = relationship("Signal")


class Setting(Base):
    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("org_id", "key", name="uq_setting_org_key"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    key = Column(String(100), nullable=False, index=True)
    value = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    org = relationship("Organization", back_populates="settings")
