"""The structured shape of a CV.

The LLM is asked to return JSON matching CVData, and the PDF template is
rendered from it. Everything except `name` has a default so that sparse CVs
(e.g. no projects or certifications) still validate.
"""

from pydantic import BaseModel, Field


class Contact(BaseModel):
    email: str = ""
    phone: str = ""
    location: str = ""
    links: list[str] = Field(default_factory=list)


class Experience(BaseModel):
    title: str
    company: str = ""  # can be empty, e.g. freelance or self-employed roles
    location: str = ""
    start: str = ""  # kept as free text: CVs use "2021", "Jan 2021", "01/2021"...
    end: str = ""
    bullets: list[str] = Field(default_factory=list)


class Education(BaseModel):
    degree: str
    institution: str = ""
    start: str = ""
    end: str = ""
    details: list[str] = Field(default_factory=list)


class SkillGroup(BaseModel):
    category: str = ""
    items: list[str] = Field(default_factory=list)


class Project(BaseModel):
    name: str
    description: str = ""
    bullets: list[str] = Field(default_factory=list)


class OtherSection(BaseModel):
    """Catch-all for sections that don't fit above (languages, awards, volunteering...)."""

    heading: str
    items: list[str] = Field(default_factory=list)


class CVData(BaseModel):
    name: str
    contact: Contact = Field(default_factory=Contact)
    summary: str = ""
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[SkillGroup] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    other_sections: list[OtherSection] = Field(default_factory=list)
